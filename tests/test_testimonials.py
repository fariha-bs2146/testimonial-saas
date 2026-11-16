from fastapi.testclient import TestClient
from sqlmodel import Session
from app.models import Embed, Space, Testimonial, User
from app.services.auth_service import hash_password


def test_submit_testimonial_success(client: TestClient, session: Session, free_user: User):
    """Test successful public testimonial submission with ratings."""
    space_resp = client.post("/spaces", json={"name": "Widget Co", "enable_rating": True})
    space_id = space_resp.json()["id"]

    payload = {
        "customer_name": "Sarah Connor",
        "customer_email": "sarah@cyberdyne.com",
        "company_name": "Resistance Inc.",
        "testimonial_text": "Saved our operations in record time!",
        "rating": 5,
        "sharing_consent": True,
    }
    resp = client.post(f"/spaces/{space_id}/testimonials", json=payload)
    assert resp.status_code == 201
    data = resp.json()
    assert data["customer_name"] == "Sarah Connor"
    assert data["rating"] == 5
    assert data["is_favorite"] is False
    assert data["is_wall_of_love"] is False
    assert data["is_hidden"] is False
    assert data["space_id"] == space_id


def test_submit_testimonial_by_slug(client: TestClient):
    """Test public submission using space's public slug."""
    client.post("/spaces", json={"name": "Slug Space", "public_slug": "slug-space-test"})

    payload = {
        "customer_name": "John Matrix",
        "customer_email": "john@valverde.com",
        "testimonial_text": "Let off some steam with this great tool!",
        "rating": 4,
    }
    resp = client.post("/s/slug-space-test/testimonials", json=payload)
    assert resp.status_code == 201
    assert resp.json()["customer_name"] == "John Matrix"


def test_submit_testimonial_invalid_rating(client: TestClient):
    """Test submitting invalid star rating returns 422."""
    space_resp = client.post("/spaces", json={"name": "Rating Test", "enable_rating": True})
    space_id = space_resp.json()["id"]

    # Rating 6 is out of bounds (1-5)
    resp = client.post(
        f"/spaces/{space_id}/testimonials",
        json={
            "customer_name": "Bad Rating",
            "customer_email": "bad@example.com",
            "testimonial_text": "Too many stars!",
            "rating": 6,
        },
    )
    assert resp.status_code == 422


def test_submit_testimonial_rating_disabled(client: TestClient):
    """Test that rating is stored as None if space has enable_rating=False."""
    space_resp = client.post("/spaces", json={"name": "No Stars Space", "enable_rating": False})
    space_id = space_resp.json()["id"]

    resp = client.post(
        f"/spaces/{space_id}/testimonials",
        json={
            "customer_name": "Alice",
            "customer_email": "alice@example.com",
            "testimonial_text": "Good service",
            "rating": 5,
        },
    )
    assert resp.status_code == 201
    assert resp.json()["rating"] is None


def test_free_plan_testimonial_limit(client: TestClient, session: Session, free_user: User):
    """
    Test that a Space on the Free plan strictly enforces the 100 testimonials limit.
    The 101st testimonial submission must fail with HTTP 403 Forbidden.
    """
    space_resp = client.post("/spaces", json={"name": "Free Limit Space"})
    space_id = space_resp.json()["id"]

    # Pre-populate space with 100 testimonials directly in database
    for i in range(100):
        t = Testimonial(
            space_id=space_id,
            customer_name=f"Customer {i}",
            customer_email=f"customer{i}@example.com",
            testimonial_text="Great experience!",
            rating=5,
        )
        session.add(t)
    session.commit()

    # Attempt to submit the 101st testimonial
    payload = {
        "customer_name": "101st Customer",
        "customer_email": "101@example.com",
        "testimonial_text": "This should be rejected due to plan limits.",
    }
    resp = client.post(f"/spaces/{space_id}/testimonials", json=payload)
    assert resp.status_code == 403
    assert "testimonial limit reached" in resp.json()["detail"].lower()


def test_pro_plan_testimonial_limit(pro_client: TestClient, session: Session, pro_user: User):
    """
    Test that a Space on the Pro plan can exceed 100 testimonials (up to 1000).
    """
    space_resp = pro_client.post("/spaces", json={"name": "Pro Testimonials Space"})
    space_id = space_resp.json()["id"]

    # Pre-populate 100 testimonials
    for i in range(100):
        t = Testimonial(
            space_id=space_id,
            customer_name=f"Pro Customer {i}",
            customer_email=f"pro_customer{i}@example.com",
            testimonial_text="Pro review",
        )
        session.add(t)
    session.commit()

    # The 101st testimonial must succeed on Pro plan
    payload = {
        "customer_name": "101st Pro Customer",
        "customer_email": "101pro@example.com",
        "testimonial_text": "Pro plan allows up to 1000!",
    }
    resp = pro_client.post(f"/spaces/{space_id}/testimonials", json=payload)
    assert resp.status_code == 201
    assert resp.json()["customer_name"] == "101st Pro Customer"


def test_curation_dashboard_and_filtering(client: TestClient, session: Session, free_user: User):
    """Test listing space testimonials with filter query param."""
    space_resp = client.post("/spaces", json={"name": "Curation Space"})
    space_id = space_resp.json()["id"]

    # Create 3 testimonials with different flags
    t1 = Testimonial(space_id=space_id, customer_name="Normal", customer_email="n@a.com", testimonial_text="Hi")
    t2 = Testimonial(space_id=space_id, customer_name="Fav", customer_email="f@a.com", testimonial_text="Hi", is_favorite=True)
    t3 = Testimonial(space_id=space_id, customer_name="Wall", customer_email="w@a.com", testimonial_text="Hi", is_wall_of_love=True)
    session.add_all([t1, t2, t3])
    session.commit()

    # All
    resp_all = client.get(f"/spaces/{space_id}/testimonials?filter=all")
    assert resp_all.status_code == 200
    assert len(resp_all.json()) == 3

    # Favorites filter
    resp_fav = client.get(f"/spaces/{space_id}/testimonials?filter=favorites")
    assert resp_fav.status_code == 200
    assert len(resp_fav.json()) == 1
    assert resp_fav.json()[0]["customer_name"] == "Fav"

    # Wall of Love filter
    resp_wall = client.get(f"/spaces/{space_id}/testimonials?filter=wall_of_love")
    assert resp_wall.status_code == 200
    assert len(resp_wall.json()) == 1
    assert resp_wall.json()[0]["customer_name"] == "Wall"


def test_curation_toggle_flags(client: TestClient):
    """Test toggling favorite, wall of love, and hidden curation flags."""
    space_resp = client.post("/spaces", json={"name": "Toggle Space"})
    space_id = space_resp.json()["id"]

    sub_resp = client.post(
        f"/spaces/{space_id}/testimonials",
        json={"customer_name": "Flag Tester", "customer_email": "ft@example.com", "testimonial_text": "Review text"},
    )
    t_id = sub_resp.json()["id"]

    # 1. Toggle Favorite
    fav_resp = client.post(f"/testimonials/{t_id}/favorite")
    assert fav_resp.status_code == 200
    assert fav_resp.json()["is_favorite"] is True

    fav_off = client.post(f"/testimonials/{t_id}/favorite")
    assert fav_off.json()["is_favorite"] is False

    # 2. Toggle Wall of Love
    wall_resp = client.post(f"/testimonials/{t_id}/wall-of-love")
    assert wall_resp.status_code == 200
    assert wall_resp.json()["is_wall_of_love"] is True

    # 3. Toggle Hide
    hide_resp = client.post(f"/testimonials/{t_id}/hide")
    assert hide_resp.status_code == 200
    assert hide_resp.json()["is_hidden"] is True


def test_curation_patch_update(client: TestClient):
    """Test updating curation flags via PATCH /testimonials/{id}."""
    space_resp = client.post("/spaces", json={"name": "Patch Space"})
    space_id = space_resp.json()["id"]

    sub_resp = client.post(
        f"/spaces/{space_id}/testimonials",
        json={"customer_name": "Patch Tester", "customer_email": "pt@example.com", "testimonial_text": "Original text"},
    )
    t_id = sub_resp.json()["id"]

    patch_resp = client.patch(
        f"/testimonials/{t_id}",
        json={
            "is_favorite": True,
            "is_wall_of_love": True,
            "is_hidden": False,
            "testimonial_text": "Edited text",
        },
    )
    assert patch_resp.status_code == 200
    data = patch_resp.json()
    assert data["is_favorite"] is True
    assert data["is_wall_of_love"] is True
    assert data["testimonial_text"] == "Edited text"


def test_delete_testimonial(client: TestClient):
    """Test space owner deleting a testimonial."""
    space_resp = client.post("/spaces", json={"name": "Delete Test Space"})
    space_id = space_resp.json()["id"]

    sub_resp = client.post(
        f"/spaces/{space_id}/testimonials",
        json={"customer_name": "To Delete", "customer_email": "del@example.com", "testimonial_text": "Goodbye"},
    )
    t_id = sub_resp.json()["id"]

    del_resp = client.delete(f"/testimonials/{t_id}")
    assert del_resp.status_code == 200

    # Testimonial should now be gone
    get_resp = client.get(f"/testimonials/{t_id}")
    assert get_resp.status_code == 404


def test_curation_non_owner_forbidden(client: TestClient, session: Session):
    """Test that a non-owner cannot curate or delete another user's testimonials."""
    # User 2 owns a space & testimonial
    user2 = User(email="user2@example.com", hashed_password=hash_password("pw"))
    session.add(user2)
    session.commit()
    session.refresh(user2)

    s2 = Space(user_id=user2.id, name="User2 Space", title="", subtitle="", ask="", public_slug="user2-space")
    session.add(s2)
    session.commit()
    session.refresh(s2)

    t2 = Testimonial(space_id=s2.id, customer_name="Cust", customer_email="c@b.com", testimonial_text="Nice")
    session.add(t2)
    session.commit()
    session.refresh(t2)

    # client is authenticated as free_user (User 1), attempting to curate User 2's testimonial
    resp = client.post(f"/testimonials/{t2.id}/favorite")
    assert resp.status_code == 403

    del_resp = client.delete(f"/testimonials/{t2.id}")
    assert del_resp.status_code == 403


def test_embed_code_generation_and_crud(client: TestClient):
    """Test creating embed configuration and retrieving generated iframe & script codes."""
    space_resp = client.post("/spaces", json={"name": "Embed Test Space"})
    space_id = space_resp.json()["id"]

    # 1. Create embed
    create_resp = client.post(
        f"/spaces/{space_id}/embeds",
        json={
            "space_id": space_id,
            "display_style": "masonry",
            "theme_mode": "dark",
            "background_color": "#0f172a",
            "animation_enabled": True,
            "content_filter": "wall_of_love",
        },
    )
    assert create_resp.status_code == 201
    embed_id = create_resp.json()["id"]
    assert create_resp.json()["display_style"] == "masonry"

    # 2. Get embed with generated code snippets
    get_resp = client.get(f"/embeds/{embed_id}")
    assert get_resp.status_code == 200
    data = get_resp.json()
    assert "codes" in data
    assert f"/embed/{embed_id}" in data["codes"]["iframe"]
    assert "<iframe" in data["codes"]["iframe"]
    assert f"kudospace-embed-{embed_id}" in data["codes"]["script"]

    # 3. Update embed
    update_resp = client.patch(
        f"/embeds/{embed_id}",
        json={"display_style": "carousel", "theme_mode": "light"},
    )
    assert update_resp.status_code == 200
    assert update_resp.json()["display_style"] == "carousel"
    assert update_resp.json()["theme_mode"] == "light"

    # 4. Delete embed
    del_resp = client.delete(f"/embeds/{embed_id}")
    assert del_resp.status_code == 200


def test_public_embed_widgets_masonry_and_carousel(client: TestClient, session: Session, free_user: User):
    """Test public widget views for masonry and carousel styles."""
    space_resp = client.post("/spaces", json={"name": "Widget Display Space"})
    space_id = space_resp.json()["id"]

    # Add 2 testimonials
    client.post(
        f"/spaces/{space_id}/testimonials",
        json={"customer_name": "Happy Customer 1", "customer_email": "c1@ex.com", "testimonial_text": "Loved the masonry layout!"},
    )
    client.post(
        f"/spaces/{space_id}/testimonials",
        json={"customer_name": "Happy Customer 2", "customer_email": "c2@ex.com", "testimonial_text": "Loved the carousel layout!"},
    )

    # Embed 1: Masonry
    m_resp = client.post(f"/spaces/{space_id}/embeds", json={"space_id": space_id, "display_style": "masonry"})
    m_id = m_resp.json()["id"]

    widget_m = client.get(f"/embed/{m_id}")
    assert widget_m.status_code == 200
    assert "masonry-columns" in widget_m.text
    assert "Loved the masonry layout!" in widget_m.text

    # Embed 2: Carousel
    c_resp = client.post(f"/spaces/{space_id}/embeds", json={"space_id": space_id, "display_style": "carousel"})
    c_id = c_resp.json()["id"]

    widget_c = client.get(f"/embed/{c_id}")
    assert widget_c.status_code == 200
    assert "carousel-slide" in widget_c.text
    assert "nextSlide" in widget_c.text


def test_embed_content_filter_and_hidden_exclusion(client: TestClient, session: Session, free_user: User):
    """Test that widget honors content_filter='wall_of_love' and excludes hidden testimonials."""
    space_resp = client.post("/spaces", json={"name": "Filter Widget Space"})
    space_id = space_resp.json()["id"]

    # Testimonial A: Standard uncurated
    client.post(
        f"/spaces/{space_id}/testimonials",
        json={"customer_name": "Standard Testimonial", "customer_email": "std@ex.com", "testimonial_text": "Regular feedback."},
    )

    # Testimonial B: Added to Wall of Love
    t2_resp = client.post(
        f"/spaces/{space_id}/testimonials",
        json={"customer_name": "Wall of Love Testimonial", "customer_email": "wall@ex.com", "testimonial_text": "Sensational product!"},
    )
    t2_id = t2_resp.json()["id"]
    client.post(f"/testimonials/{t2_id}/wall-of-love")

    # Testimonial C: Hidden testimonial (should never appear)
    t3_resp = client.post(
        f"/spaces/{space_id}/testimonials",
        json={"customer_name": "Hidden Testimonial", "customer_email": "hidden@ex.com", "testimonial_text": "Secret feedback."},
    )
    t3_id = t3_resp.json()["id"]
    client.post(f"/testimonials/{t3_id}/hide")

    # Embed configured for wall_of_love only
    embed_resp = client.post(
        f"/spaces/{space_id}/embeds",
        json={"space_id": space_id, "content_filter": "wall_of_love"},
    )
    embed_id = embed_resp.json()["id"]

    view = client.get(f"/embed/{embed_id}")
    assert view.status_code == 200
    assert "Sensational product!" in view.text
    assert "Regular feedback." not in view.text
    assert "Secret feedback." not in view.text
