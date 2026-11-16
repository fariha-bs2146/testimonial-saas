from datetime import datetime, timezone
import os
from typing import Any, Dict, List, Optional
from fastapi import APIRouter, Depends, Form, HTTPException, Request, Response, status
from fastapi.responses import HTMLResponse, JSONResponse, PlainTextResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlmodel import Session, func, select

from app.database import get_session
from app.models import (
    Embed,
    EmbedCreate,
    EmbedRead,
    EmbedUpdate,
    Space,
    Testimonial,
    TestimonialCreate,
    TestimonialRead,
    TestimonialUpdate,
    User,
)
from app.services.auth_service import get_current_user
from app.services.plan_service import (
    PLAN_LIMITS,
    check_testimonial_limit,
    count_space_testimonials,
    get_user_plan,
)

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
templates = Jinja2Templates(directory=os.path.join(BASE_DIR, "templates"))

router = APIRouter()


def generate_embed_code(embed: Embed, base_url: str = "") -> Dict[str, str]:
    """Generate ready-to-use HTML iframe and script tags for an embed widget."""
    base_url = base_url.rstrip("/")
    iframe_code = (
        f'<iframe src="{base_url}/embed/{embed.id}" '
        f'width="100%" height="600" frameborder="0" '
        f'scrolling="auto" loading="lazy" style="border:none; width:100%; min-height:500px;"></iframe>'
    )
    script_code = (
        f'<div id="kudospace-embed-{embed.id}"></div>\n'
        f'<script src="{base_url}/embed/{embed.id}/widget.js" async></script>'
    )
    return {
        "iframe": iframe_code,
        "script": script_code,
        "url": f"{base_url}/embed/{embed.id}",
    }


# ==========================================
# 1. Public Testimonial Submission
# ==========================================

@router.post("/spaces/{space_id}/testimonials", response_model=TestimonialRead, status_code=status.HTTP_201_CREATED)
def submit_testimonial(
    space_id: int,
    payload: TestimonialCreate,
    session: Session = Depends(get_session),
):
    """
    Public endpoint for customers to submit a testimonial to a space.
    Enforces PlanService limits and validates star rating.
    """
    space = session.get(Space, space_id)
    if not space:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Space not found")

    # Enforce Plan Testimonial Limits (Free: 100, Pro: 1000)
    check_testimonial_limit(space, session)

    # Validate Rating if enabled
    final_rating = payload.rating
    if space.enable_rating:
        if final_rating is not None:
            if final_rating < 1 or final_rating > 5:
                raise HTTPException(
                    status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                    detail="Rating must be between 1 and 5 stars.",
                )
    else:
        final_rating = None

    testimonial = Testimonial(
        space_id=space.id,
        customer_name=payload.customer_name,
        customer_email=payload.customer_email,
        company_name=payload.company_name,
        social_links=payload.social_links,
        profile_photo_url=payload.profile_photo_url,
        testimonial_text=payload.testimonial_text,
        rating=final_rating,
        sharing_consent=payload.sharing_consent,
        is_favorite=False,
        is_wall_of_love=False,
        is_hidden=False,
        submitted_at=datetime.now(timezone.utc),
    )
    session.add(testimonial)
    session.commit()
    session.refresh(testimonial)
    return testimonial


@router.post("/s/{public_slug}/testimonials", response_model=TestimonialRead, status_code=status.HTTP_201_CREATED)
def submit_testimonial_by_slug(
    public_slug: str,
    payload: TestimonialCreate,
    session: Session = Depends(get_session),
):
    """Convenience public submission endpoint using space's public slug."""
    statement = select(Space).where(Space.public_slug == public_slug)
    space = session.exec(statement).first()
    if not space:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Space not found")
    return submit_testimonial(space_id=space.id, payload=payload, session=session)


@router.post("/s/{public_slug}/submit-form", response_class=HTMLResponse)
def submit_testimonial_form(
    public_slug: str,
    request: Request,
    customer_name: str = Form(...),
    customer_email: str = Form(...),
    testimonial_text: str = Form(...),
    company_name: Optional[str] = Form(None),
    rating: Optional[int] = Form(None),
    sharing_consent: bool = Form(True),
    session: Session = Depends(get_session),
):
    """HTML form submission handler for public testimonial pages."""
    statement = select(Space).where(Space.public_slug == public_slug)
    space = session.exec(statement).first()
    if not space:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Space not found")

    payload = TestimonialCreate(
        customer_name=customer_name,
        customer_email=customer_email,
        testimonial_text=testimonial_text,
        company_name=company_name,
        rating=rating,
        sharing_consent=sharing_consent,
    )
    try:
        submit_testimonial(space_id=space.id, payload=payload, session=session)
        return templates.TemplateResponse(
            request=request,
            name="testimonials/submitted.html",
            context={"space": space, "customer_name": customer_name},
        )
    except HTTPException as e:
        return templates.TemplateResponse(
            request=request,
            name="spaces/public_space.html",
            context={"space": space, "error": e.detail},
            status_code=e.status_code,
        )


# ==========================================
# 2. Space Owner Dashboard & Curation
# ==========================================

@router.get("/spaces/{space_id}/testimonials", response_model=List[TestimonialRead])
def list_space_testimonials(
    space_id: int,
    request: Request,
    filter: Optional[str] = "all",
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
):
    """
    Space owner dashboard to view and curate testimonials.
    Filters: all | favorites | wall_of_love | hidden.
    """
    space = session.get(Space, space_id)
    if not space or space.user_id != current_user.id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Space not found")

    statement = select(Testimonial).where(Testimonial.space_id == space_id)
    if filter == "favorites":
        statement = statement.where(Testimonial.is_favorite == True)
    elif filter == "wall_of_love":
        statement = statement.where(Testimonial.is_wall_of_love == True)
    elif filter == "hidden":
        statement = statement.where(Testimonial.is_hidden == True)

    statement = statement.order_by(Testimonial.submitted_at.desc())
    testimonials = session.exec(statement).all()

    accept = request.headers.get("accept", "")
    if "text/html" in accept and "application/json" not in accept:
        # Calculate stats for the dashboard
        all_count = session.exec(select(func.count(Testimonial.id)).where(Testimonial.space_id == space_id)).one() or 0
        fav_count = session.exec(select(func.count(Testimonial.id)).where(Testimonial.space_id == space_id, Testimonial.is_favorite == True)).one() or 0
        wall_count = session.exec(select(func.count(Testimonial.id)).where(Testimonial.space_id == space_id, Testimonial.is_wall_of_love == True)).one() or 0
        hidden_count = session.exec(select(func.count(Testimonial.id)).where(Testimonial.space_id == space_id, Testimonial.is_hidden == True)).one() or 0

        plan = get_user_plan(current_user)
        limits = PLAN_LIMITS[plan]

        return templates.TemplateResponse(
            request=request,
            name="testimonials/dashboard.html",
            context={
                "space": space,
                "testimonials": testimonials,
                "current_filter": filter,
                "stats": {
                    "total": all_count,
                    "favorites": fav_count,
                    "wall_of_love": wall_count,
                    "hidden": hidden_count,
                },
                "plan": plan,
                "limits": limits,
                "user": current_user,
            },
        )

    return testimonials


@router.get("/testimonials/{testimonial_id}", response_model=TestimonialRead)
def get_testimonial(
    testimonial_id: int,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
):
    """Get single testimonial by ID for the space owner."""
    testimonial = session.get(Testimonial, testimonial_id)
    if not testimonial:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Testimonial not found")

    space = session.get(Space, testimonial.space_id)
    if not space or space.user_id != current_user.id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not authorized to view this testimonial")

    return testimonial


@router.patch("/testimonials/{testimonial_id}", response_model=TestimonialRead)
@router.put("/testimonials/{testimonial_id}", response_model=TestimonialRead)
def update_testimonial(
    testimonial_id: int,
    payload: TestimonialUpdate,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
):
    """
    Curate/update a testimonial (is_favorite, is_wall_of_love, is_hidden, rating, text).
    Only the owner of the space can update its testimonials.
    """
    testimonial = session.get(Testimonial, testimonial_id)
    if not testimonial:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Testimonial not found")

    space = session.get(Space, testimonial.space_id)
    if not space or space.user_id != current_user.id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not authorized to edit this testimonial")

    if payload.is_favorite is not None:
        testimonial.is_favorite = payload.is_favorite
    if payload.is_wall_of_love is not None:
        testimonial.is_wall_of_love = payload.is_wall_of_love
    if payload.is_hidden is not None:
        testimonial.is_hidden = payload.is_hidden
    if payload.testimonial_text is not None:
        testimonial.testimonial_text = payload.testimonial_text
    if payload.rating is not None:
        if payload.rating < 1 or payload.rating > 5:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail="Rating must be between 1 and 5")
        testimonial.rating = payload.rating
    if payload.customer_name is not None:
        testimonial.customer_name = payload.customer_name
    if payload.company_name is not None:
        testimonial.company_name = payload.company_name

    session.add(testimonial)
    session.commit()
    session.refresh(testimonial)
    return testimonial


@router.post("/testimonials/{testimonial_id}/favorite", response_model=TestimonialRead)
def toggle_favorite(
    testimonial_id: int,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
):
    """Quick API toggle for favorite status."""
    testimonial = session.get(Testimonial, testimonial_id)
    if not testimonial:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Testimonial not found")

    space = session.get(Space, testimonial.space_id)
    if not space or space.user_id != current_user.id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not authorized")

    testimonial.is_favorite = not testimonial.is_favorite
    session.add(testimonial)
    session.commit()
    session.refresh(testimonial)
    return testimonial


@router.post("/testimonials/{testimonial_id}/wall-of-love", response_model=TestimonialRead)
def toggle_wall_of_love(
    testimonial_id: int,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
):
    """Quick API toggle for Wall of Love status."""
    testimonial = session.get(Testimonial, testimonial_id)
    if not testimonial:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Testimonial not found")

    space = session.get(Space, testimonial.space_id)
    if not space or space.user_id != current_user.id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not authorized")

    testimonial.is_wall_of_love = not testimonial.is_wall_of_love
    session.add(testimonial)
    session.commit()
    session.refresh(testimonial)
    return testimonial


@router.post("/testimonials/{testimonial_id}/hide", response_model=TestimonialRead)
def toggle_hide(
    testimonial_id: int,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
):
    """Quick API toggle for hidden status."""
    testimonial = session.get(Testimonial, testimonial_id)
    if not testimonial:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Testimonial not found")

    space = session.get(Space, testimonial.space_id)
    if not space or space.user_id != current_user.id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not authorized")

    testimonial.is_hidden = not testimonial.is_hidden
    session.add(testimonial)
    session.commit()
    session.refresh(testimonial)
    return testimonial


@router.delete("/testimonials/{testimonial_id}", status_code=status.HTTP_200_OK)
def delete_testimonial(
    testimonial_id: int,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
):
    """Permanently delete a testimonial. Owner only."""
    testimonial = session.get(Testimonial, testimonial_id)
    if not testimonial:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Testimonial not found")

    space = session.get(Space, testimonial.space_id)
    if not space or space.user_id != current_user.id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not authorized to delete this testimonial")

    session.delete(testimonial)
    session.commit()
    return {"message": "Testimonial deleted successfully", "id": testimonial_id}


# Form Action Handlers for Web Dashboard
@router.post("/testimonials/{testimonial_id}/toggle-favorite")
def form_toggle_favorite(
    testimonial_id: int,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
):
    t = toggle_favorite(testimonial_id=testimonial_id, session=session, current_user=current_user)
    return RedirectResponse(url=f"/spaces/{t.space_id}/testimonials", status_code=status.HTTP_303_SEE_OTHER)


@router.post("/testimonials/{testimonial_id}/toggle-wall")
def form_toggle_wall(
    testimonial_id: int,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
):
    t = toggle_wall_of_love(testimonial_id=testimonial_id, session=session, current_user=current_user)
    return RedirectResponse(url=f"/spaces/{t.space_id}/testimonials", status_code=status.HTTP_303_SEE_OTHER)


@router.post("/testimonials/{testimonial_id}/toggle-hide")
def form_toggle_hide(
    testimonial_id: int,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
):
    t = toggle_hide(testimonial_id=testimonial_id, session=session, current_user=current_user)
    return RedirectResponse(url=f"/spaces/{t.space_id}/testimonials", status_code=status.HTTP_303_SEE_OTHER)


@router.post("/testimonials/{testimonial_id}/delete-form")
def form_delete_testimonial(
    testimonial_id: int,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
):
    testimonial = session.get(Testimonial, testimonial_id)
    if not testimonial:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Testimonial not found")
    space_id = testimonial.space_id
    delete_testimonial(testimonial_id=testimonial_id, session=session, current_user=current_user)
    return RedirectResponse(url=f"/spaces/{space_id}/testimonials", status_code=status.HTTP_303_SEE_OTHER)


# ==========================================
# 3. Embed Widgets & Code Generation
# ==========================================

@router.post("/spaces/{space_id}/embeds", response_model=EmbedRead, status_code=status.HTTP_201_CREATED)
def create_embed(
    space_id: int,
    payload: EmbedCreate,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
):
    """Create an embed configuration for a space."""
    space = session.get(Space, space_id)
    if not space or space.user_id != current_user.id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Space not found")

    embed = Embed(
        user_id=current_user.id,
        space_id=space_id,
        display_style=payload.display_style,
        theme_mode=payload.theme_mode,
        background_color=payload.background_color or "#ffffff",
        animation_enabled=payload.animation_enabled,
        content_filter=payload.content_filter,
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )
    session.add(embed)
    session.commit()
    session.refresh(embed)
    return embed


@router.get("/spaces/{space_id}/embeds", response_model=List[EmbedRead])
def list_space_embeds(
    space_id: int,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
):
    """List all embed configurations for a space."""
    space = session.get(Space, space_id)
    if not space or space.user_id != current_user.id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Space not found")

    statement = select(Embed).where(Embed.space_id == space_id).order_by(Embed.created_at.desc())
    return session.exec(statement).all()


@router.get("/spaces/{space_id}/embeds/view", response_class=HTMLResponse)
def embed_configurator_view(
    space_id: int,
    request: Request,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
):
    """HTML dashboard page to configure, preview, and copy embed widget codes."""
    space = session.get(Space, space_id)
    if not space or space.user_id != current_user.id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Space not found")

    # Get or create default embed
    statement = select(Embed).where(Embed.space_id == space_id)
    embed = session.exec(statement).first()
    if not embed:
        embed = Embed(
            user_id=current_user.id,
            space_id=space_id,
            display_style="masonry",
            theme_mode="light",
            background_color="#ffffff",
            animation_enabled=True,
            content_filter="all",
        )
        session.add(embed)
        session.commit()
        session.refresh(embed)

    base_url = str(request.base_url).rstrip("/")
    codes = generate_embed_code(embed, base_url=base_url)

    plan = get_user_plan(current_user)
    return templates.TemplateResponse(
        request=request,
        name="embeds/configurator.html",
        context={
            "space": space,
            "embed": embed,
            "codes": codes,
            "user": current_user,
            "plan": plan,
        },
    )


@router.get("/embeds/{embed_id}")
def get_embed(
    embed_id: int,
    request: Request,
    session: Session = Depends(get_session),
):
    """Retrieve embed configuration along with generated HTML code snippets."""
    embed = session.get(Embed, embed_id)
    if not embed:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Embed configuration not found")

    base_url = str(request.base_url).rstrip("/")
    codes = generate_embed_code(embed, base_url=base_url)

    return {
        "embed": embed,
        "codes": codes,
    }


@router.put("/embeds/{embed_id}", response_model=EmbedRead)
@router.patch("/embeds/{embed_id}", response_model=EmbedRead)
def update_embed(
    embed_id: int,
    payload: EmbedUpdate,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
):
    """Update embed configuration (style, theme, filter, background)."""
    embed = session.get(Embed, embed_id)
    if not embed or embed.user_id != current_user.id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Embed not found")

    if payload.display_style is not None:
        embed.display_style = payload.display_style
    if payload.theme_mode is not None:
        embed.theme_mode = payload.theme_mode
    if payload.background_color is not None:
        embed.background_color = payload.background_color
    if payload.animation_enabled is not None:
        embed.animation_enabled = payload.animation_enabled
    if payload.content_filter is not None:
        embed.content_filter = payload.content_filter

    embed.updated_at = datetime.now(timezone.utc)
    session.add(embed)
    session.commit()
    session.refresh(embed)
    return embed


@router.delete("/embeds/{embed_id}", status_code=status.HTTP_200_OK)
def delete_embed(
    embed_id: int,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
):
    """Delete an embed configuration."""
    embed = session.get(Embed, embed_id)
    if not embed or embed.user_id != current_user.id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Embed not found")

    session.delete(embed)
    session.commit()
    return {"message": "Embed deleted successfully", "id": embed_id}


# ==========================================
# 4. Public Widget Views (Masonry & Carousel)
# ==========================================

@router.get("/embed/{embed_id}", response_class=HTMLResponse)
def render_embed_widget(
    embed_id: int,
    request: Request,
    session: Session = Depends(get_session),
):
    """
    Public widget endpoint rendered inside an iframe or web page.
    Supports 'masonry' and 'carousel' display styles, light/dark themes, and filters.
    """
    embed = session.get(Embed, embed_id)
    if not embed:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Embed not found")

    space = session.get(Space, embed.space_id)
    if not space:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Space not found")

    # Fetch non-hidden testimonials matching the content filter
    statement = (
        select(Testimonial)
        .where(Testimonial.space_id == embed.space_id)
        .where(Testimonial.is_hidden == False)
    )
    if embed.content_filter == "wall_of_love":
        statement = statement.where(Testimonial.is_wall_of_love == True)

    statement = statement.order_by(Testimonial.submitted_at.desc())
    testimonials = session.exec(statement).all()

    return templates.TemplateResponse(
        request=request,
        name="embeds/widget.html",
        context={
            "embed": embed,
            "space": space,
            "testimonials": testimonials,
        },
    )


@router.get("/embed/{embed_id}/widget.js", response_class=PlainTextResponse)
def render_embed_js_loader(
    embed_id: int,
    request: Request,
    session: Session = Depends(get_session),
):
    """JavaScript embed loader script that injects an iframe dynamically."""
    embed = session.get(Embed, embed_id)
    if not embed:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Embed not found")

    base_url = str(request.base_url).rstrip("/")
    js_content = f"""
(function() {{
    var container = document.getElementById('kudospace-embed-{embed_id}');
    if (!container) return;
    var iframe = document.createElement('iframe');
    iframe.src = '{base_url}/embed/{embed_id}';
    iframe.width = '100%';
    iframe.height = '600';
    iframe.frameBorder = '0';
    iframe.style.border = 'none';
    iframe.style.width = '100%';
    iframe.style.minHeight = '500px';
    container.appendChild(iframe);
}})();
"""
    return PlainTextResponse(content=js_content.strip(), media_type="application/javascript")
