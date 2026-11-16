from contextlib import asynccontextmanager
import os
from fastapi import Depends, FastAPI, Request
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles
from sqlmodel import Session

from app.database import get_session, init_db
from app.routers import billing, spaces, testimonials

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
STATIC_DIR = os.path.join(BASE_DIR, "static")


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Initialize SQLite database & tables
    init_db()
    yield


app = FastAPI(
    title="Testimonial SaaS",
    description="Customer testimonial collection platform with customizable themes and embed widgets.",
    version="1.0.0",
    lifespan=lifespan,
)

# Ensure static directory exists and mount it
os.makedirs(STATIC_DIR, exist_ok=True)
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

# Include spaces router under both /spaces and /api/spaces
app.include_router(spaces.router, prefix="/spaces", tags=["spaces"])
app.include_router(spaces.router, prefix="/api/spaces", tags=["api-spaces"])

# Include testimonials & embeds router
app.include_router(testimonials.router, tags=["testimonials", "embeds"])
app.include_router(testimonials.router, prefix="/api", tags=["api-testimonials"])

# Include billing router
app.include_router(billing.router, prefix="/billing", tags=["billing"])
app.include_router(billing.router, prefix="/api/billing", tags=["api-billing"])


@app.get("/", include_in_schema=False)
def root():
    return RedirectResponse(url="/spaces")


@app.get("/s/{public_slug}", tags=["public-collection"])
def public_collection_page(
    public_slug: str,
    request: Request,
    session: Session = Depends(get_session),
):
    """Convenience shortcut to view public testimonial collection page at /s/{public_slug}."""
    return spaces.get_public_space(public_slug=public_slug, request=request, session=session)
