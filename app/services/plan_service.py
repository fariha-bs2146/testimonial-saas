import os
from typing import Any, Dict, Optional
from fastapi import HTTPException, status
from sqlmodel import Session, func, select
import stripe

from app.models import Space, Testimonial, User
# Re-export auth utilities for convenience
from app.services.auth_service import (
    get_current_user,
    get_or_create_default_user,
    hash_password,
    verify_password,
)

PLAN_FREE = "free"
PLAN_PRO = "pro"

PLAN_LIMITS: Dict[str, Dict[str, int]] = {
    PLAN_FREE: {
        "max_spaces": 3,
        "max_testimonials_per_space": 100,
    },
    PLAN_PRO: {
        "max_spaces": 25,
        "max_testimonials_per_space": 1000,
    },
}

# In-memory registry to track subscription statuses (updated via webhooks, testing, and API)
SUBSCRIPTION_STATUS_REGISTRY: Dict[str, str] = {}


def set_customer_subscription_status(stripe_customer_id: str, status_name: str) -> None:
    """Store or update subscription status for a Stripe customer."""
    SUBSCRIPTION_STATUS_REGISTRY[stripe_customer_id] = status_name


def get_customer_subscription_status(stripe_customer_id: str) -> Optional[str]:
    """Retrieve current subscription status for a customer."""
    return SUBSCRIPTION_STATUS_REGISTRY.get(stripe_customer_id)


def clear_subscription_status_registry() -> None:
    """Clear registry cache (useful for test teardown)."""
    SUBSCRIPTION_STATUS_REGISTRY.clear()


def check_stripe_subscription_status(stripe_customer_id: Optional[str]) -> bool:
    """
    Dynamically verify if a Stripe customer has an active or trialing subscription.
    Checks subscription registry cache first, then calls Stripe API if configured.
    """
    if not stripe_customer_id:
        return False

    # 1. Check dynamic subscription status registry (e.g. from webhooks or mocks)
    status_val = SUBSCRIPTION_STATUS_REGISTRY.get(stripe_customer_id)
    if status_val is not None:
        return status_val in ("active", "trialing")

    # 2. Check live Stripe API if secret key is present
    api_key = os.getenv("STRIPE_SECRET_KEY") or getattr(stripe, "api_key", None)
    if not api_key:
        return False

    stripe.api_key = api_key
    try:
        subscriptions = stripe.Subscription.list(
            customer=stripe_customer_id,
            status="active",
            limit=1,
        )
        if hasattr(subscriptions, "data") and len(subscriptions.data) > 0:
            return True

        # Check trialing status as well
        trialing = stripe.Subscription.list(
            customer=stripe_customer_id,
            status="trialing",
            limit=1,
        )
        return bool(hasattr(trialing, "data") and len(trialing.data) > 0)
    except Exception:
        return False


def get_user_plan(user: User) -> str:
    """
    Dynamically returns user's plan: 'pro' if Stripe subscription is active, otherwise 'free'.
    Supports:
      1. Mock flag '_is_pro' on user
      2. Dynamic subscription registry from Stripe webhooks
      3. Live Stripe Subscription API check
    """
    if getattr(user, "_is_pro", None) is not None:
        return PLAN_PRO if user._is_pro else PLAN_FREE

    if user.stripe_customer_id:
        if check_stripe_subscription_status(user.stripe_customer_id):
            return PLAN_PRO

    return PLAN_FREE


def get_plan_limits(plan_name: str) -> Dict[str, int]:
    return PLAN_LIMITS.get(plan_name, PLAN_LIMITS[PLAN_FREE])


def count_user_spaces(user_id: int, session: Session) -> int:
    statement = select(func.count(Space.id)).where(Space.user_id == user_id)
    return session.exec(statement).one() or 0


def count_space_testimonials(space_id: int, session: Session) -> int:
    statement = select(func.count(Testimonial.id)).where(Testimonial.space_id == space_id)
    return session.exec(statement).one() or 0


def can_create_space(user: User, session: Session) -> bool:
    plan = get_user_plan(user)
    limit = PLAN_LIMITS[plan]["max_spaces"]
    current_count = count_user_spaces(user.id, session)
    return current_count < limit


def check_space_creation_limit(user: User, session: Session) -> None:
    """
    Raises HTTP 403 Forbidden if user has exceeded their plan's space limit.
    """
    plan = get_user_plan(user)
    limit = PLAN_LIMITS[plan]["max_spaces"]
    current_count = count_user_spaces(user.id, session)
    if current_count >= limit:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=(
                f"Free plan limit reached: {limit} spaces max. "
                "Upgrade to Pro for up to 25 spaces."
                if plan == PLAN_FREE
                else f"Pro plan limit reached: {limit} spaces max."
            ),
        )


def can_add_testimonial(space: Space, session: Session) -> bool:
    user = session.get(User, space.user_id)
    plan = get_user_plan(user) if user else PLAN_FREE
    limit = PLAN_LIMITS[plan]["max_testimonials_per_space"]
    current_count = count_space_testimonials(space.id, session)
    return current_count < limit


def check_testimonial_limit(space: Space, session: Session) -> None:
    """
    Raises HTTP 403 Forbidden if testimonial count exceeds the space's plan limit.
    """
    user = session.get(User, space.user_id)
    plan = get_user_plan(user) if user else PLAN_FREE
    limit = PLAN_LIMITS[plan]["max_testimonials_per_space"]
    current_count = count_space_testimonials(space.id, session)
    if current_count >= limit:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=(
                f"Testimonial limit reached ({current_count}/{limit}) for "
                f"{plan.capitalize()} plan."
            ),
        )
