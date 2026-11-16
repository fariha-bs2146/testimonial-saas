# Testimonial SaaS - Agentic Engineering Project

A production-ready Testimonial SaaS platform built using **FastAPI (Python 3.12)**, **SQLite / SQLModel**, **Tailwind CSS**, **Stripe Billing**, and **Pytest**. Developed as part of the Agentic Engineering training curriculum.

## 🚀 Key Features
1. **Spaces & Themes**: Create customized testimonial collection spaces supporting multiple themes (`minimal`, `modern`, `classic`), custom headings, and star rating toggles.
2. **Public Collection & Validation**: Public submission forms with star rating checks, metadata collection, and plan quota limit enforcement.
3. **Curation Dashboard**: Space owners can filter, favorite, feature on the "Wall of Love", hide, or delete testimonials.
4. **Embed Widgets**: Generate responsive `iframe` and JavaScript embed codes with `masonry` and `carousel` display styles. 
5. **Stripe Billing Integration**: Full checkout session creation, customer portal management, and robust webhook event handlers.

---

## 🛠️ Tech Stack
- **Backend**: FastAPI, SQLModel, SQLAlchemy, Pydantic, Python-Multipart
- **Database**: SQLite (`database.db`)
- **Frontend**: Jinja2 Templates, Tailwind CSS
- **Billing**: Stripe Python SDK & Webhooks
- **Testing**: Pytest, FastAPI TestClient, StaticPool

---

## ⚙️ Setup & Installation
1. **Navigate to Project**: `cd ~/projects/Agentic_AI/testimonial-saas`
2. **Activate Virtual Environment**: `source venv/bin/activate`
3. **Run Development Server**: `uvicorn app.main:app --reload --port 8000`

---

## 🧪 Running the Test Suite
```bash
pytest -v
```
