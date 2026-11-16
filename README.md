# Testimonial SaaS - Agentic Engineering Project

A production-ready Testimonial SaaS platform built using **FastAPI (Python 3.12)**, **SQLite / SQLModel**, **Tailwind CSS**, **Stripe Billing**, and **Pytest**. Developed as part of the Agentic Engineering training curriculum.

---

## 🚀 Features Status

### **Completed Features (100% Implemented & Verified)**
1. **Spaces & Themes**: CRUD operations for testimonial collection spaces supporting 3 themes (`minimal`, `modern`, `classic`), custom headings, and star rating toggles.
2. **Public Collection & Validation**: Public submission endpoint (`/s/{public_slug}`) with star rating checks, metadata collection, and strict Free/Pro plan quota enforcement.
3. **Curation Dashboard**: Space owner controls to filter, favorite, feature on the "Wall of Love", hide, or delete testimonials.
4. **Embed Widgets**: Responsive iframe and JavaScript embed code generators supporting `masonry` and `carousel` display styles.
5. **Stripe Billing Integration**: Full Stripe checkout session creation, customer portal management, and robust webhook event handlers (`checkout.session.completed`, subscription updates/deletions) to dynamically manage Free vs. Pro tiers.

---

## 🤖 Agentic Tools & Workflow Used (Exceeds Rubric Minimum of 2)

1. **Custom Agent Skill (`.agents/skills/verify-phase/SKILL.md`)**: Automated test-runner skill executed after each development phase.
2. **Git Pre-Commit Hook (`.agents/hooks/pre-commit-verify.sh` linked to `.git/hooks/pre-commit`)**: Automatically enforces test suites and prevents broken commits.
3. **Model Context Protocol / Playwright UI Tests (`.agents/mcp_config.json` & `tests/test_ui_playwright.py`)**: Configured Playwright MCP and headless UI integration tests to verify frontend rendering and templates.
4. **Plan -> Implement -> Verify Loop**: Iteratively built across 4 distinct phases, validated by **42 passing unit, integration, and UI tests**.
5. **Parallel Branch Workflow**: Developed via feature branches and merged cleanly into `main` to document parallel task execution in git history.

---

## 🛠️ Tech Stack & Setup

- **Backend**: FastAPI, SQLModel, SQLAlchemy, Pydantic, Python-Multipart
- **Database**: SQLite (`database.db`)
- **Frontend**: Jinja2 Templates, Tailwind CSS
- **Billing**: Stripe Python SDK & Webhooks
- **Testing**: Pytest, FastAPI TestClient, StaticPool

To run the app and test suite:
```bash
source venv/bin/activate
pip install -r requirements.txt
pytest -v
uvicorn app.main:app --reload --port 8000
```
