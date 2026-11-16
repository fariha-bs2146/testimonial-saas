from fastapi.testclient import TestClient
from sqlmodel import Session, select
from app.models import Space, User
from app.services.plan_service import (
    PLAN_LIMITS,
    can_create_space,
    count_user_spaces,
    get_user_plan,
)


def test_create_space_minimal(client: TestClient):
    """Test creating a space with minimal theme."""
    payload = {
        "name": "Acme SaaS",
        "title": "Loved by thousands of teams",
        "subtitle": "Share your experience with our product",
        "ask": "How has Acme helped your team save time?",
        "theme": "minimal",
        "enable_rating": True,
        "public_slug": "acme-saas",
    }
    response = client.post("/spaces", json=payload)
    assert response.status_code == 201
    data = response.json()
    assert data["name"] == "Acme SaaS"
    assert data["public_slug"] == "acme-saas"
    assert data["theme"] == "minimal"
    assert data["enable_rating"] is True
    assert "id" in data


def test_create_space_all_valid_themes(client: TestClient):
    """Test creating spaces with modern and classic themes."""
    # Modern theme
    resp_modern = client.post(
        "/spaces",
        json={"name": "Modern App", "theme": "modern", "public_slug": "modern-app"},
    )
    assert resp_modern.status_code == 201
    assert resp_modern.json()["theme"] == "modern"

    # Classic theme
    resp_classic = client.post(
        "/spaces",
        json={"name": "Classic Firm", "theme": "classic", "public_slug": "classic-firm"},
    )
    assert resp_classic.status_code == 201
    assert resp_classic.json()["theme"] == "classic"


def test_create_space_invalid_theme(client: TestClient):
    """Test creating a space with an invalid theme fails with 422."""
    payload = {
        "name": "Invalid Theme Space",
        "theme": "futuristic-neon",
    }
    response = client.post("/spaces", json=payload)
    assert response.status_code == 422


def test_slug_uniqueness_explicit(client: TestClient):
    """Test that two spaces cannot have the same explicit public_slug."""
    payload1 = {
        "name": "Alpha Space",
        "public_slug": "unique-slug",
    }
    resp1 = client.post("/spaces", json=payload1)
    assert resp1.status_code == 201

    payload2 = {
        "name": "Beta Space",
        "public_slug": "unique-slug",
    }
    resp2 = client.post("/spaces", json=payload2)
    assert resp2.status_code == 400
    assert "already exists" in resp2.json()["detail"].lower()


def test_slug_auto_generation_and_uniqueness(client: TestClient):
    """Test that omitting public_slug auto-generates a unique slug from name."""
    # First space
    resp1 = client.post("/spaces", json={"name": "Duplicate Name"})
    assert resp1.status_code == 201
    slug1 = resp1.json()["public_slug"]
    assert slug1 == "duplicate-name"

    # Second space with identical name
    resp2 = client.post("/spaces", json={"name": "Duplicate Name"})
    assert resp2.status_code == 201
    slug2 = resp2.json()["public_slug"]
    assert slug2 == "duplicate-name-1"
    assert slug1 != slug2


def test_free_plan_space_limit(client: TestClient):
    """
    Test that users on the Free plan are strictly limited to 3 spaces.
    The 4th space creation must fail with 403 Forbidden.
    """
    # Create 3 spaces (max allowed on Free plan)
    for i in range(1, 4):
        resp = client.post(
            "/spaces",
            json={"name": f"Free Space {i}", "public_slug": f"free-space-{i}"},
        )
        assert resp.status_code == 201, f"Failed creating space {i}: {resp.text}"

    # Attempt to create the 4th space
    resp4 = client.post(
        "/spaces",
        json={"name": "Free Space 4", "public_slug": "free-space-4"},
    )
    assert resp4.status_code == 403
    assert "free plan limit reached" in resp4.json()["detail"].lower()
    assert "3 spaces max" in resp4.json()["detail"].lower()


def test_pro_plan_space_limit(pro_client: TestClient):
    """
    Test that users on the Pro plan can create more than 3 spaces (up to 25).
    """
    for i in range(1, 6):
        resp = pro_client.post(
            "/spaces",
            json={"name": f"Pro Space {i}", "public_slug": f"pro-space-{i}"},
        )
        assert resp.status_code == 201, f"Failed creating pro space {i}: {resp.text}"


def test_list_spaces(client: TestClient, session: Session, free_user: User):
    """Test listing spaces only returns spaces owned by the current user."""
    client.post("/spaces", json={"name": "User 1 Space A"})
    client.post("/spaces", json={"name": "User 1 Space B"})

    # Create another user and space directly in DB
    other_user = User(email="other@example.com", hashed_password="pw")
    session.add(other_user)
    session.commit()
    session.refresh(other_user)

    other_space = Space(
        user_id=other_user.id,
        name="Other User Space",
        title="Other",
        subtitle="",
        ask="",
        public_slug="other-user-space",
    )
    session.add(other_space)
    session.commit()

    # User 1 lists spaces
    response = client.get("/spaces")
    assert response.status_code == 200
    spaces = response.json()
    assert len(spaces) == 2
    slugs = [s["public_slug"] for s in spaces]
    assert "other-user-space" not in slugs


def test_get_space_by_id(client: TestClient):
    """Test retrieving an existing space by ID."""
    create_resp = client.post(
        "/spaces",
        json={"name": "Get Test", "title": "My Title", "public_slug": "get-test"},
    )
    space_id = create_resp.json()["id"]

    get_resp = client.get(f"/spaces/{space_id}")
    assert get_resp.status_code == 200
    assert get_resp.json()["name"] == "Get Test"

    # Non-existent space
    not_found_resp = client.get("/spaces/99999")
    assert not_found_resp.status_code == 404


def test_update_space(client: TestClient):
    """Test updating space fields including theme, name, and enable_rating."""
    create_resp = client.post(
        "/spaces",
        json={"name": "Original Name", "theme": "minimal", "public_slug": "original-slug"},
    )
    space_id = create_resp.json()["id"]

    # Update name and theme
    update_resp = client.put(
        f"/spaces/{space_id}",
        json={"name": "Updated Name", "theme": "classic", "enable_rating": False},
    )
    assert update_resp.status_code == 200
    updated = update_resp.json()
    assert updated["name"] == "Updated Name"
    assert updated["theme"] == "classic"
    assert updated["enable_rating"] is False

    # Attempt to update to an existing slug
    client.post("/spaces", json={"name": "Another", "public_slug": "taken-slug"})
    conflict_resp = client.put(
        f"/spaces/{space_id}",
        json={"public_slug": "taken-slug"},
    )
    assert conflict_resp.status_code == 400


def test_delete_space(client: TestClient):
    """Test deleting a space."""
    create_resp = client.post(
        "/spaces",
        json={"name": "To Delete", "public_slug": "to-delete"},
    )
    space_id = create_resp.json()["id"]

    del_resp = client.delete(f"/spaces/{space_id}")
    assert del_resp.status_code == 200

    # Verify space is gone
    get_resp = client.get(f"/spaces/{space_id}")
    assert get_resp.status_code == 404


def test_public_space_endpoint(client: TestClient):
    """Test public collection endpoints (/s/{slug} and /spaces/public/{slug})."""
    client.post(
        "/spaces",
        json={
            "name": "Public Showcase",
            "title": "Tell us what you love",
            "theme": "modern",
            "public_slug": "public-showcase",
        },
    )

    # Public JSON retrieval
    json_resp = client.get("/spaces/public/public-showcase", headers={"Accept": "application/json"})
    assert json_resp.status_code == 200
    assert json_resp.json()["public_slug"] == "public-showcase"

    # Public HTML page retrieval
    html_resp = client.get("/s/public-showcase")
    assert html_resp.status_code == 200
    assert "Tell us what you love" in html_resp.text
    assert "Modern Theme" in html_resp.text or "Share Your Story" in html_resp.text
