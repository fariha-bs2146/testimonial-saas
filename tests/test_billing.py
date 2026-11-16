import json
from fastapi.testclient import TestClient
from sqlmodel import Session
import stripe
from app.models import User
from app.services.plan_service import (
    clear_subscription_status_registry,
    get_user_plan,
)


def test_billing_settings_free_user(client: TestClient, free_user: User):
    """Test retrieving billing settings for a Free tier user."""
    # JSON API view
    resp = client.get("/billing", headers={"Accept": "application/json"})
    assert resp.status_code == 200
    data = resp.json()
    assert data["plan"] == "free"
    assert data["limits"]["max_spaces"] == 3
    assert data["limits"]["max_testimonials_per_space"] == 100
    assert data["email"] == free_user.email

    # HTML page view
    html_resp = client.get("/billing")
    assert html_resp.status_code == 200
    assert "Free Starter Plan" in html_resp.text
    assert "Upgrade to Pro" in html_resp.text


def test_billing_settings_pro_user(pro_client: TestClient, pro_user: User):
    """Test retrieving billing settings for a Pro tier user."""
    # JSON API view
    resp = pro_client.get("/billing", headers={"Accept": "application/json"})
    assert resp.status_code == 200
    data = resp.json()
    assert data["plan"] == "pro"
    assert data["limits"]["max_spaces"] == 25
    assert data["limits"]["max_testimonials_per_space"] == 1000

    # HTML page view
    html_resp = pro_client.get("/billing")
    assert html_resp.status_code == 200
    assert "Pro Plan" in html_resp.text
    assert "Active Pro" in html_resp.text
    assert "Manage via Stripe Portal" in html_resp.text


def test_create_checkout_session(client: TestClient):
    """Test creating a Stripe checkout session."""
    resp = client.post("/billing/create-checkout-session")
    assert resp.status_code == 200
    data = resp.json()
    assert "url" in data
    assert "session_id" in data
    assert "status=success" in data["url"]


def test_create_checkout_session_with_stripe_api(client: TestClient, monkeypatch):
    """Test checkout session creation calls stripe.checkout.Session.create when API key configured."""
    monkeypatch.setenv("STRIPE_SECRET_KEY", "sk_test_mock_123")

    class MockSession:
        url = "https://checkout.stripe.com/pay/cs_mock_123"
        id = "cs_mock_123"

    called_params = {}

    def mock_create(**kwargs):
        called_params.update(kwargs)
        return MockSession()

    monkeypatch.setattr(stripe.checkout.Session, "create", mock_create)

    resp = client.post("/billing/create-checkout-session")
    assert resp.status_code == 200
    assert resp.json()["url"] == "https://checkout.stripe.com/pay/cs_mock_123"
    assert resp.json()["session_id"] == "cs_mock_123"
    assert called_params["mode"] == "subscription"


def test_create_portal_session_pro_user(pro_client: TestClient):
    """Test creating a billing portal session for a customer with stripe_customer_id."""
    resp = pro_client.post("/billing/create-portal-session")
    assert resp.status_code == 200
    assert "url" in resp.json()


def test_create_portal_session_free_user_fails(client: TestClient):
    """Test creating a portal session without stripe_customer_id returns 400."""
    resp = client.post("/billing/create-portal-session")
    assert resp.status_code == 400
    assert "no stripe customer found" in resp.json()["detail"].lower()


def test_webhook_checkout_session_completed_links_user(client: TestClient, session: Session, free_user: User):
    """
    Test handling checkout.session.completed webhook event:
    Verifies user.stripe_customer_id is updated and plan transitions to Pro.
    """
    clear_subscription_status_registry()

    payload = {
        "id": "evt_test_checkout",
        "type": "checkout.session.completed",
        "data": {
            "object": {
                "id": "cs_test_completed_123",
                "customer": "cus_upgraded_999",
                "client_reference_id": str(free_user.id),
                "customer_details": {"email": free_user.email},
            }
        },
    }

    resp = client.post(
        "/billing/webhook",
        content=json.dumps(payload),
        headers={"Content-Type": "application/json"},
    )
    assert resp.status_code == 200
    assert resp.json()["status"] == "success"

    # Verify user updated in database
    session.refresh(free_user)
    assert free_user.stripe_customer_id == "cus_upgraded_999"

    # Plan should now dynamically be Pro
    assert get_user_plan(free_user) == "pro"


def test_webhook_subscription_lifecycle_transitions(client: TestClient, session: Session, free_user: User):
    """
    Test customer.subscription.updated webhook event:
    Verifies transition from active -> canceled -> active.
    """
    clear_subscription_status_registry()
    customer_id = "cus_lifecycle_test"
    free_user.stripe_customer_id = customer_id
    session.add(free_user)
    session.commit()
    session.refresh(free_user)

    # 1. Subscription updated to active -> user is Pro
    payload_active = {
        "id": "evt_sub_active",
        "type": "customer.subscription.updated",
        "data": {
            "object": {
                "id": "sub_123",
                "customer": customer_id,
                "status": "active",
            }
        },
    }
    resp1 = client.post("/billing/webhook", content=json.dumps(payload_active))
    assert resp1.status_code == 200
    assert resp1.json()["subscription_status"] == "active"
    assert get_user_plan(free_user) == "pro"

    # 2. Subscription updated to canceled -> user falls back to Free
    payload_canceled = {
        "id": "evt_sub_canceled",
        "type": "customer.subscription.updated",
        "data": {
            "object": {
                "id": "sub_123",
                "customer": customer_id,
                "status": "canceled",
            }
        },
    }
    resp2 = client.post("/billing/webhook", content=json.dumps(payload_canceled))
    assert resp2.status_code == 200
    assert resp2.json()["subscription_status"] == "canceled"
    assert get_user_plan(free_user) == "free"

    # 3. Subscription deleted -> user remains Free
    payload_deleted = {
        "id": "evt_sub_deleted",
        "type": "customer.subscription.deleted",
        "data": {
            "object": {
                "id": "sub_123",
                "customer": customer_id,
            }
        },
    }
    resp3 = client.post("/billing/webhook", content=json.dumps(payload_deleted))
    assert resp3.status_code == 200
    assert get_user_plan(free_user) == "free"


def test_webhook_signature_verification_error(client: TestClient, monkeypatch):
    """Test webhook with invalid signature returns 400 when STRIPE_WEBHOOK_SECRET is set."""
    monkeypatch.setenv("STRIPE_WEBHOOK_SECRET", "whsec_supersecret123")

    payload = {"type": "checkout.session.completed"}
    resp = client.post(
        "/billing/webhook",
        content=json.dumps(payload),
        headers={"stripe-signature": "invalid_sig_header"},
    )
    assert resp.status_code == 400
    assert "signature verification failed" in resp.json()["detail"].lower()
