"""Plan enforcement: usage counting, limit checks, and feature gating.

This is the one place that answers "is business X allowed to do Y right
now". Routers call these helpers instead of re-deriving limits themselves,
so a plan change in app/core/plans.py takes effect everywhere at once.
"""
from dataclasses import asdict
from datetime import datetime, timezone
from typing import Optional

from fastapi import HTTPException
from sqlalchemy import func
from sqlalchemy.orm import Session

from ..core.plans import PLANS, Plan, get_plan, NOT_YET_IMPLEMENTED_FEATURES
from ..models.business import Business
from ..models.document import Document
from ..models.product import Product
from ..models.conversation import Conversation
from ..models.website import BusinessWebsite


def _current_month_start() -> datetime:
    now = datetime.now(timezone.utc)
    return now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)


def get_usage(db: Session, business_id) -> dict:
    """Raw counts against the current plan's countable resources."""
    websites = db.query(func.count(BusinessWebsite.id)).filter(
        BusinessWebsite.business_id == business_id
    ).scalar() or 0

    conversations_this_month = db.query(func.count(Conversation.id)).filter(
        Conversation.business_id == business_id,
        Conversation.started_at >= _current_month_start(),
    ).scalar() or 0

    documents = db.query(func.count(Document.id)).filter(
        Document.business_id == business_id
    ).scalar() or 0

    products = db.query(func.count(Product.id)).filter(
        Product.business_id == business_id
    ).scalar() or 0

    return {
        "websites": websites,
        "conversations_this_month": conversations_this_month,
        "documents": documents,
        "products": products,
    }


def resolve_features(business: Business) -> dict:
    """Plan features, adjusted for per-business overrides.

    Right now the only override is API access: Business-tier customers
    don't get it by default, but can buy the add-on (business.api_access_addon).
    Growth includes it outright, so the add-on flag is irrelevant there.
    """
    plan = get_plan(business.plan)
    features = asdict(plan.features)
    features["api_access"] = plan.features.api_access or (
        plan.key == "business" and bool(business.api_access_addon)
    )
    return features


def get_plan_status(db: Session, business: Business) -> dict:
    plan = get_plan(business.plan)
    return {
        "plan": plan.key,
        "plan_name": plan.name,
        "price_usd": plan.price_usd,
        "limits": asdict(plan.limits),
        "usage": get_usage(db, business.id),
        "features": resolve_features(business),
        "api_access_addon": bool(business.api_access_addon),
        "not_yet_implemented": sorted(NOT_YET_IMPLEMENTED_FEATURES),
    }


def get_plan_catalog() -> list[dict]:
    """Public plan list for pricing/upgrade UI -- no business context needed."""
    return [
        {
            "key": plan.key,
            "name": plan.name,
            "price_usd": plan.price_usd,
            "tagline": plan.tagline,
            "limits": asdict(plan.limits),
            "features": asdict(plan.features),
        }
        for plan in PLANS.values()
    ]


def _raise_limit_reached(limit: int, resource_label: str):
    raise HTTPException(
        status_code=402,
        detail=(
            f"Your plan's limit of {limit} {resource_label} has been reached. "
            "Upgrade your plan to add more."
        ),
    )


def check_website_limit(db: Session, business: Business) -> None:
    plan = get_plan(business.plan)
    if plan.limits.max_websites is None:
        return
    count = db.query(func.count(BusinessWebsite.id)).filter(
        BusinessWebsite.business_id == business.id
    ).scalar() or 0
    if count >= plan.limits.max_websites:
        _raise_limit_reached(plan.limits.max_websites, "websites")


def check_document_limit(db: Session, business: Business) -> None:
    plan = get_plan(business.plan)
    if plan.limits.max_document_uploads is None:
        return
    count = db.query(func.count(Document.id)).filter(
        Document.business_id == business.id
    ).scalar() or 0
    if count >= plan.limits.max_document_uploads:
        _raise_limit_reached(plan.limits.max_document_uploads, "document uploads")


def check_product_limit(db: Session, business: Business) -> None:
    plan = get_plan(business.plan)
    if plan.limits.max_products is None:
        return
    count = db.query(func.count(Product.id)).filter(
        Product.business_id == business.id
    ).scalar() or 0
    if count >= plan.limits.max_products:
        _raise_limit_reached(plan.limits.max_products, "products")


def check_conversation_limit(db: Session, business: Business) -> None:
    """Called only when a *new* conversation is about to start -- an
    in-progress conversation that started before the cap was hit is never
    interrupted mid-thread."""
    plan = get_plan(business.plan)
    if plan.limits.max_conversations_per_month is None:
        return
    count = db.query(func.count(Conversation.id)).filter(
        Conversation.business_id == business.id,
        Conversation.started_at >= _current_month_start(),
    ).scalar() or 0
    if count >= plan.limits.max_conversations_per_month:
        raise HTTPException(
            status_code=402,
            detail=(
                "This business has reached its plan's monthly AI conversation limit. "
                "Please try again next month, or ask the site owner to upgrade their plan."
            ),
        )


def check_language_limit(business: Business, requested_languages: list) -> None:
    plan = get_plan(business.plan)
    if plan.limits.max_languages is None:
        return
    if len(requested_languages) > plan.limits.max_languages:
        raise HTTPException(
            status_code=402,
            detail=(
                f"Your plan supports up to {plan.limits.max_languages} language(s). "
                "Upgrade your plan to add more."
            ),
        )


def require_feature(business: Business, feature_key: str) -> None:
    """Gate an action behind a boolean feature flag.

    Raises 403 if the plan doesn't include the feature at all, or 501 if
    the plan includes it but the feature itself isn't built yet (see
    NOT_YET_IMPLEMENTED_FEATURES in app/core/plans.py) -- distinguishing
    "upgrade to unlock" from "this doesn't exist yet" instead of
    pretending an unbuilt integration works.
    """
    plan = get_plan(business.plan)
    features = resolve_features(business)
    if not features.get(feature_key):
        raise HTTPException(
            status_code=403,
            detail=f"'{feature_key}' isn't available on the {plan.name} plan. Upgrade to unlock it.",
        )
    if feature_key in NOT_YET_IMPLEMENTED_FEATURES:
        raise HTTPException(
            status_code=501,
            detail=f"'{feature_key}' is coming soon and isn't available yet.",
        )


def resolve_analytics_tier(business: Business) -> str:
    return get_plan(business.plan).features.analytics_tier
