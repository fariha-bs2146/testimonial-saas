# Testimonial SaaS - Agentic Engineering Project

A production-ready Testimonial SaaS platform built using **FastAPI (Python 3.12)**, **SQLite / SQLModel**, **Tailwind CSS**, **Stripe Billing**, and **Pytest**. Developed as part of the Agentic Engineering training curriculum.

---

## 🚀 Features Status

### **Completed Features (100% Implemented & Verified)**
1. **Spaces & Themes**: CRUD operations for testimonial collection spaces supporting 3 themes (`minimal`, `modern`, `classic`), custom headings, and star rating toggles.
2. **Public Collection & Validation**: Public submission endpoint (`/s/{public_slug}`) with star rating checks, metadata collection (company name, social links), and strict Free/Pro plan quota enforcement.
3. **Curation Dashboard**: Space owner controls to filter, favorite, feature on the "Wall of Love", hide, or delete testimonials.
4. **Embed Widgets**: Responsive iframe and JavaScript embed code generators supporting `masonry` and `carousel` display styles.
5. **Stripe Billing Integration**: Full Stripe checkout session creation, customer portal management, and robust webhook event handlers (`checkout.session.completed`, subscription updates/deletions) to dynamically manage Free vs. Pro tiers.

### **Future / Stretch Features (Not in MVP)**
- Video testimonial recording uploads (currently text and star ratings).
- Advanced team member permission roles per space.

---

## 🤖 Agentic Tools & Workflow Used

- **`CLAUDE.md` / `GEMINI.md`**: Strict rule definitions and framework guidelines enforcing Pydantic validation, SQLModel structuring, and plan limit rules for AI code generation.
- **Custom Agent Skill (`.agents/skills/verify-phase/SKILL.md`)**: Automated skill executed after each development phase to run and verify the `pytest` test suite.
- **Model Context Protocol (`.agents/mcp_config.json`)**: Configured with Playwright MCP (`@playwright/mcp`) for headless browser automation and UI testing.
- **Plan -> Implement -> Verify Loop**: Iteratively built across 4 distinct phases, validated by **41 passing unit and integration tests**.
- **Parallel Branch Workflow**: Developed via feature branches and merged cleanly into `main` to document parallel task execution in git history.

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
3. **Install Dependencies**: `pip install -r requirements.txt`
4. **Run Development Server**: `uvicorn app.main:app --reload --port 8000` (Access at `http://localhost:8000`)

---

## 🧪 Running the Test Suite

```bash
pytest -v
```
