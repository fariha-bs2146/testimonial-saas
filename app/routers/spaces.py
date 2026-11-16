from datetime import datetime, timezone
import os
import re
from typing import Any, Dict, List, Optional
from fastapi import APIRouter, Depends, Form, HTTPException, Request, Response, status
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlmodel import Session, select

from app.database import get_session
from app.models import (
    Space,
    SpaceCreate,
    SpaceRead,
    SpaceUpdate,
    User,
    VALID_THEMES,
)
from app.services.auth_service import get_current_user
from app.services.plan_service import (
    PLAN_LIMITS,
    check_space_creation_limit,
    count_user_spaces,
    get_user_plan,
)

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
templates = Jinja2Templates(directory=os.path.join(BASE_DIR, "templates"))

router = APIRouter()


def slugify(text: str) -> str:
    text = text.lower().strip()
    text = re.sub(r"[^\w\s-]", "", text)
    text = re.sub(r"[\s_-]+", "-", text)
    text = re.sub(r"^-+|-+$", "", text)
    return text or "space"


def generate_unique_slug(base_text: str, session: Session, exclude_id: Optional[int] = None) -> str:
    base_slug = slugify(base_text)
    slug = base_slug
    counter = 1
    while True:
        statement = select(Space).where(Space.public_slug == slug)
        if exclude_id is not None:
            statement = statement.where(Space.id != exclude_id)
        existing = session.exec(statement).first()
        if not existing:
            return slug
        slug = f"{base_slug}-{counter}"
        counter += 1


# ==========================================
# Space List & Creation (JSON API + HTML)
# ==========================================

@router.get("", response_model=List[SpaceRead])
def list_spaces(
    request: Request,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
):
    """
    List all spaces belonging to the authenticated user.
    Renders HTML if requested by a browser, otherwise returns JSON list.
    """
    statement = (
        select(Space)
        .where(Space.user_id == current_user.id)
        .order_by(Space.created_at.desc())
    )
    spaces = session.exec(statement).all()

    accept = request.headers.get("accept", "")
    if "text/html" in accept and "application/json" not in accept:
        plan = get_user_plan(current_user)
        limits = PLAN_LIMITS[plan]
        return templates.TemplateResponse(
            request=request,
            name="spaces/list.html",
            context={
                "spaces": spaces,
                "user": current_user,
                "plan": plan,
                "limits": limits,
                "used_spaces": len(spaces),
            },
        )

    return spaces


@router.post("", response_model=SpaceRead, status_code=status.HTTP_201_CREATED)
def create_space(
    payload: SpaceCreate,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
):
    """
    Create a new space for the current user.
    Enforces plan limits, unique slug, and theme validation.
    """
    # 1. Enforce Plan Limits (Free: 3 spaces, Pro: 25 spaces)
    check_space_creation_limit(current_user, session)

    # 2. Validate theme
    if payload.theme not in VALID_THEMES:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=f"Invalid theme '{payload.theme}'. Must be one of: {', '.join(sorted(VALID_THEMES))}",
        )

    # 3. Handle public slug & uniqueness
    if payload.public_slug:
        candidate_slug = slugify(payload.public_slug)
        # Check uniqueness
        statement = select(Space).where(Space.public_slug == candidate_slug)
        if session.exec(statement).first():
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Public slug '{candidate_slug}' already exists. Please choose a different slug.",
            )
        final_slug = candidate_slug
    else:
        final_slug = generate_unique_slug(payload.name, session)

    # 4. Create and persist Space
    title = payload.title or payload.name
    space = Space(
        user_id=current_user.id,
        name=payload.name,
        title=title,
        subtitle=payload.subtitle or "",
        ask=payload.ask or "",
        theme=payload.theme,
        enable_rating=payload.enable_rating,
        field_configuration=payload.field_configuration or {},
        public_slug=final_slug,
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )
    session.add(space)
    session.commit()
    session.refresh(space)
    return space


# ==========================================
# Template Pages (UI navigation)
# ==========================================

@router.get("/new", response_class=HTMLResponse)
def new_space_page(
    request: Request,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
):
    """Render the HTML page to create a new space."""
    plan = get_user_plan(current_user)
    limits = PLAN_LIMITS[plan]
    used = count_user_spaces(current_user.id, session)
    return templates.TemplateResponse(
        request=request,
        name="spaces/form.html",
        context={
            "user": current_user,
            "space": None,
            "is_edit": False,
            "plan": plan,
            "limits": limits,
            "limit_reached": (used >= limits["max_spaces"]),
        },
    )


@router.post("/form")
def create_space_from_form(
    request: Request,
    name: str = Form(...),
    title: Optional[str] = Form(None),
    subtitle: Optional[str] = Form(""),
    ask: Optional[str] = Form(""),
    theme: str = Form("minimal"),
    enable_rating: bool = Form(False),
    public_slug: Optional[str] = Form(None),
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
):
    """HTML form submission handler to create a new space."""
    payload = SpaceCreate(
        name=name,
        title=title or name,
        subtitle=subtitle or "",
        ask=ask or "",
        theme=theme if theme in VALID_THEMES else "minimal",
        enable_rating=enable_rating,
        public_slug=public_slug if public_slug and public_slug.strip() else None,
    )
    try:
        space = create_space(payload=payload, session=session, current_user=current_user)
        return RedirectResponse(url=f"/spaces/{space.id}", status_code=status.HTTP_303_SEE_OTHER)
    except HTTPException as e:
        plan = get_user_plan(current_user)
        limits = PLAN_LIMITS[plan]
        used = count_user_spaces(current_user.id, session)
        return templates.TemplateResponse(
            request=request,
            name="spaces/form.html",
            context={
                "user": current_user,
                "space": None,
                "is_edit": False,
                "plan": plan,
                "limits": limits,
                "limit_reached": (used >= limits["max_spaces"]),
                "error": e.detail,
            },
            status_code=e.status_code,
        )


@router.get("/{space_id}/edit", response_class=HTMLResponse)
def edit_space_page(
    space_id: int,
    request: Request,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
):
    """Render HTML form to edit an existing space."""
    space = session.get(Space, space_id)
    if not space or space.user_id != current_user.id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Space not found")

    plan = get_user_plan(current_user)
    limits = PLAN_LIMITS[plan]
    return templates.TemplateResponse(
        request=request,
        name="spaces/form.html",
        context={
            "user": current_user,
            "space": space,
            "is_edit": True,
            "plan": plan,
            "limits": limits,
            "limit_reached": False,
        },
    )


@router.post("/{space_id}/edit-form")
def edit_space_from_form(
    space_id: int,
    request: Request,
    name: str = Form(...),
    title: Optional[str] = Form(None),
    subtitle: Optional[str] = Form(""),
    ask: Optional[str] = Form(""),
    theme: str = Form("minimal"),
    enable_rating: bool = Form(False),
    public_slug: Optional[str] = Form(None),
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
):
    """HTML form submission handler to edit an existing space."""
    payload = SpaceUpdate(
        name=name,
        title=title,
        subtitle=subtitle,
        ask=ask,
        theme=theme if theme in VALID_THEMES else "minimal",
        enable_rating=enable_rating,
        public_slug=public_slug if public_slug and public_slug.strip() else None,
    )
    try:
        update_space(space_id=space_id, payload=payload, session=session, current_user=current_user)
        return RedirectResponse(url=f"/spaces/{space_id}", status_code=status.HTTP_303_SEE_OTHER)
    except HTTPException as e:
        space = session.get(Space, space_id)
        plan = get_user_plan(current_user)
        limits = PLAN_LIMITS[plan]
        return templates.TemplateResponse(
            request=request,
            name="spaces/form.html",
            context={
                "user": current_user,
                "space": space,
                "is_edit": True,
                "plan": plan,
                "limits": limits,
                "error": e.detail,
            },
            status_code=e.status_code,
        )


@router.post("/{space_id}/delete-form")
def delete_space_from_form(
    space_id: int,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
):
    """HTML form submission to delete a space and redirect to list."""
    delete_space(space_id=space_id, session=session, current_user=current_user)
    return RedirectResponse(url="/spaces", status_code=status.HTTP_303_SEE_OTHER)


# ==========================================
# Space Detail, Update & Delete (API + HTML)
# ==========================================

@router.get("/{space_id}", response_model=SpaceRead)
def get_space(
    space_id: int,
    request: Request,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
):
    """Retrieve details for a single space."""
    space = session.get(Space, space_id)
    if not space or space.user_id != current_user.id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Space not found")

    accept = request.headers.get("accept", "")
    if "text/html" in accept and "application/json" not in accept:
        plan = get_user_plan(current_user)
        return templates.TemplateResponse(
            request=request,
            name="spaces/detail.html",
            context={
                "space": space,
                "user": current_user,
                "plan": plan,
            },
        )

    return space


@router.put("/{space_id}", response_model=SpaceRead)
@router.patch("/{space_id}", response_model=SpaceRead)
def update_space(
    space_id: int,
    payload: SpaceUpdate,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
):
    """Update space settings (name, title, subtitle, ask, theme, slug, enable_rating)."""
    space = session.get(Space, space_id)
    if not space or space.user_id != current_user.id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Space not found")

    if payload.theme is not None:
        if payload.theme not in VALID_THEMES:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail=f"Invalid theme '{payload.theme}'. Must be one of: {', '.join(sorted(VALID_THEMES))}",
            )
        space.theme = payload.theme

    if payload.public_slug is not None:
        new_slug = slugify(payload.public_slug)
        if new_slug != space.public_slug:
            # Check if taken by another space
            statement = (
                select(Space)
                .where(Space.public_slug == new_slug)
                .where(Space.id != space.id)
            )
            if session.exec(statement).first():
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"Public slug '{new_slug}' already exists. Please choose a different slug.",
                )
            space.public_slug = new_slug

    if payload.name is not None:
        space.name = payload.name
    if payload.title is not None:
        space.title = payload.title
    if payload.subtitle is not None:
        space.subtitle = payload.subtitle
    if payload.ask is not None:
        space.ask = payload.ask
    if payload.enable_rating is not None:
        space.enable_rating = payload.enable_rating
    if payload.field_configuration is not None:
        space.field_configuration = payload.field_configuration

    space.updated_at = datetime.now(timezone.utc)
    session.add(space)
    session.commit()
    session.refresh(space)
    return space


@router.delete("/{space_id}", status_code=status.HTTP_200_OK)
def delete_space(
    space_id: int,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
):
    """Delete a space owned by the authenticated user."""
    space = session.get(Space, space_id)
    if not space or space.user_id != current_user.id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Space not found")

    session.delete(space)
    session.commit()
    return {"message": "Space deleted successfully", "id": space_id}


# ==========================================
# Public Space View by Slug
# ==========================================

@router.get("/public/{public_slug}")
def get_public_space(
    public_slug: str,
    request: Request,
    session: Session = Depends(get_session),
):
    """Public testimonial collection page for a Space."""
    statement = select(Space).where(Space.public_slug == public_slug)
    space = session.exec(statement).first()
    if not space:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Space not found")

    accept = request.headers.get("accept", "")
    if "application/json" in accept and "text/html" not in accept:
        return space

    return templates.TemplateResponse(
        request=request,
        name="spaces/public_space.html",
        context={"space": space},
    )
