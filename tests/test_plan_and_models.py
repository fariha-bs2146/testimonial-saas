from datetime import datetime, timezone
import pytest
from fastapi import HTTPException
from sqlmodel import Session
import stripe
from app.models import Embed, Space, Testimonial, User
from app.services.auth_service import hash_password, verify_password, get_or_create_default_user
from app.services.plan_service import (
    PLAN_FREE,
    PLAN_PRO,
    PLAN_LIMITS,
    can_add_testimonial,
    can_create_space,
    check_space_creation_limit,
    check_stripe_subscription_status,
    check_testimonial_limit,
    count_space_testimonials,
    count_user_spaces,
    get_user_plan,
)


def test_auth_password_hashing():
    """Verify password hashing and verification."""
    password = "SuperSecretPassword123!"
    hashed = hash_password(password)
    assert hashed != password
    assert verify_password(password, hashed) is True
    assert verify_password("WrongPassword", hashed) is False


def test_get_or_create_default_user(session: Session):
    """Verify default demo user creation."""
    user = get_or_create_default_user(session)
    assert user.id is not None
    assert user.email == "demo@example.com"

    # Calling again should retrieve the same user
    user2 = get_or_create_default_user(session)
    assert user2.id == user.id


def test_data_models_schema(session: Session):
    """Verify that User, Space, Testimonial, and Embed tables and fields match data-model.md."""
    # 1. User
    user = User(
        email="schema_test@example.com",
        hashed_password=hash_password("pw"),
        stripe_customer_id="cus_12345",
    )
    session.add(user)
    session.commit()
    session.refresh(user)
    assert user.id is not None
    assert user.created_at is not None
    assert user.updated_at is not None

    # 2. Space
    space = Space(
        user_id=user.id,
        name="Product Feedback",
        title="We value your voice",
        subtitle="Quick feedback form",
        ask="What do you love most?",
        theme="modern",
        enable_rating=True,
        field_configuration={"custom_questions": ["How did you find us?"]},
        public_slug="product-feedback-schema",
    )
    session.add(space)
    session.commit()
    session.refresh(space)
    assert space.id is not None
    assert space.theme == "modern"
    assert space.field_configuration == {"custom_questions": ["How did you find us?"]}

    # 3. Testimonial
    testimonial = Testimonial(
        space_id=space.id,
        customer_name="John Doe",
        customer_email="john@example.com",
        company_name="Acme Corp",
        social_links={"twitter": "https://twitter.com/johndoe"},
        profile_photo_url="https://example.com/avatar.jpg",
        testimonial_text="This platform increased our conversion by 40%!",
        rating=5,
        sharing_consent=True,
        is_favorite=True,
        is_wall_of_love=True,
        is_hidden=False,
    )
    session.add(testimonial)
    session.commit()
    session.refresh(testimonial)
    assert testimonial.id is not None
    assert testimonial.rating == 5
    assert testimonial.is_favorite is True
    assert testimonial.social_links == {"twitter": "https://twitter.com/johndoe"}

    # 4. Embed
    embed = Embed(
        user_id=user.id,
        space_id=space.id,
        display_style="masonry",
        theme_mode="dark",
        background_color="#0f172a",
        animation_enabled=True,
        content_filter="wall_of_love",
    )
    session.add(embed)
    session.commit()
    session.refresh(embed)
    assert embed.id is not None
    assert embed.display_style == "masonry"
    assert embed.theme_mode == "dark"
    assert embed.content_filter == "wall_of_love"


def test_plan_limits_constants():
    """Verify that plan limits match specifications."""
    assert PLAN_LIMITS[PLAN_FREE]["max_spaces"] == 3
    assert PLAN_LIMITS[PLAN_FREE]["max_testimonials_per_space"] == 100
    assert PLAN_LIMITS[PLAN_PRO]["max_spaces"] == 25
    assert PLAN_LIMITS[PLAN_PRO]["max_testimonials_per_space"] == 1000


def test_testimonial_limit_enforcement(session: Session, free_user: User):
    """Verify testimonial limit checks per space based on plan."""
    space = Space(
        user_id=free_user.id,
        name="Feedback Space",
        title="Title",
        subtitle="",
        ask="",
        public_slug="feedback-space-test",
    )
    session.add(space)
    session.commit()
    session.refresh(space)

    assert can_add_testimonial(space, session) is True
    check_testimonial_limit(space, session)  # Should not raise

    # Directly insert 100 testimonials
    for i in range(100):
        t = Testimonial(
            space_id=space.id,
            customer_name=f"Customer {i}",
            customer_email=f"customer{i}@example.com",
            testimonial_text="Great experience!",
        )
        session.add(t)
    session.commit()

    assert count_space_testimonials(space.id, session) == 100
    assert can_add_testimonial(space, session) is False

    with pytest.raises(HTTPException) as exc_info:
        check_testimonial_limit(space, session)
    assert exc_info.value.status_code == 403
    assert "testimonial limit reached" in exc_info.value.detail.lower()


def test_stripe_subscription_status_check(monkeypatch):
    """Verify Stripe subscription check returns True when active and False when inactive."""
    # Test without customer ID
    assert check_stripe_subscription_status(None) is False

    # Mock Stripe Subscription.list
    class MockData:
        data = [type("Sub", (), {"status": "active"})()]

    monkeypatch.setenv("STRIPE_SECRET_KEY", "sk_test_mock")
    monkeypatch.setattr(stripe.Subscription, "list", lambda **kwargs: MockData())

    assert check_stripe_subscription_status("cus_valid") is True

    # When no active subscriptions found
    class EmptyData:
        data = []

    monkeypatch.setattr(stripe.Subscription, "list", lambda **kwargs: EmptyData())
    assert check_stripe_subscription_status("cus_inactive") is False
