# Testimonial SaaS - Agent Rules (FastAPI Stack)
- Stack: Python 3.11 + FastAPI + SQLite + SQLModel + Tailwind CSS + Stripe Python SDK + Pytest
- Commands: 
  - Run server: `uvicorn app.main:app --reload --port 8000`
  - Run tests: `pytest`
- Rules:
  1. Use Pydantic models for request validation and SQLModel for DB operations.
  2. Enforce Free plan limits (3 Spaces, 100 testimonials/space) and Pro plan limits via Stripe subscription status in backend logic.
  3. Keep code modular across `app/models.py`, `app/database.py`, `app/routers/`, and `app/services/`.
