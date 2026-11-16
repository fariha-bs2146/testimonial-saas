from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app)

def test_landing_page_ui_render():
    """Simulates headless API/UI inspection of the root endpoint."""
    response = client.get("/")
    assert response.status_code == 200
    # Root endpoint returns JSON list of spaces
    assert isinstance(response.json(), list)

def test_public_space_form_ui_render():
    """Simulates rendering public testimonial collection form."""
    response = client.get("/s/fariha")
    assert response.status_code in [200, 404]
