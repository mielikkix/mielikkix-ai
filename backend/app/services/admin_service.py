"""Read-only queries backing the platform-admin dashboard (app/api/admin.py).

Deliberately reuses plan_service (get_usage / get_plan_status) instead of
re-deriving usage counts, and is the one place allowed to query across
businesses without a tenant filter -- every route here sits behind
require_platform_admin (see core/dependencies.py).
"""
from datetime import datetime, timedelta, timezone
from typing import Optional

from sqlalchemy import func, or_
from sqlalchemy.orm import Session

from ..core.plans import get_plan
from ..models.business import Business, BusinessSettings
from ..models.user import User
from ..models.faq import FAQ
from ..models.lead import Lead
from ..models.document import Document
from ..models.conversation import Conversation
from ..models.llm_usage import LLMUsageLog
from . import plan_service


def list_businesses(
    db: Session,
    q: Optional[str] = None,
    plan: Optional[str] = None,
    status: Optional[str] = None,
    page: int = 1,
    page_size: int = 20,
) -> dict:
    query = db.query(Business)
    if plan:
        query = query.filter(Business.plan == plan)
    if status:
        query = query.filter(Business.status == status)
    if q:
        like = f"%{q}%"
        owner_match = db.query(User.business_id).filter(User.email.ilike(like))
        query = query.filter(
            or_(Business.name.ilike(like), Business.slug.ilike(like), Business.id.in_(owner_match))
        )

    total = query.count()
    businesses = (
        query.order_by(Business.created_at.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
        .all()
    )

    items = []
    for business in businesses:
        owner = (
            db.query(User)
            .filter(User.business_id == business.id, User.role == "owner")
            .order_by(User.created_at)
            .first()
        ) or db.query(User).filter(User.business_id == business.id).order_by(User.created_at).first()
        usage = plan_service.get_usage(db, business.id)
        items.append({
            "id": business.id,
            "name": business.name,
            "slug": business.slug,
            "industry": business.industry,
            "plan": business.plan,
            "plan_name": get_plan(business.plan).name,
            "status": business.status,
            "owner_email": owner.email if owner else None,
            "owner_name": owner.full_name if owner else None,
            "created_at": business.created_at,
            "websites": usage["websites"],
            "conversations_this_month": usage["conversations_this_month"],
            "documents": usage["documents"],
            "products": usage["products"],
        })

    return {"items": items, "total": total, "page": page, "page_size": page_size}


def _llm_usage_summary(db: Session, business_id, since: datetime) -> dict:
    row = (
        db.query(
            func.count(LLMUsageLog.id),
            func.coalesce(func.sum(LLMUsageLog.prompt_tokens), 0),
            func.coalesce(func.sum(LLMUsageLog.completion_tokens), 0),
            func.coalesce(func.sum(LLMUsageLog.total_tokens), 0),
        )
        .filter(LLMUsageLog.business_id == business_id, LLMUsageLog.created_at >= since)
        .first()
    )
    requests, prompt_tokens, completion_tokens, total_tokens = row
    return {
        "requests": requests or 0,
        "prompt_tokens": prompt_tokens or 0,
        "completion_tokens": completion_tokens or 0,
        "total_tokens": total_tokens or 0,
    }


def set_business_plan(db: Session, business_id, plan: str) -> Optional[dict]:
    """Admin-only equivalent of the self-serve plan switch, minus the
    Free-only restriction -- see businesses.py:choose_plan for why that
    restriction exists. This is the one place today that can put a
    business on a paid plan at all, since no payment processor is wired up.
    `status` auto-follows the plan exactly like the self-serve endpoint
    does for Free (trial -> active on any paid plan, active -> trial on
    Free) -- unless the business is currently suspended, in which case an
    admin changing the plan doesn't silently reactivate it; use the status
    endpoint for that."""
    business = db.query(Business).filter(Business.id == business_id).first()
    if not business:
        return None

    business.plan = plan
    if business.status != "suspended":
        business.status = "trial" if plan == "free" else "active"
    if plan != "business":
        business.api_access_addon = False

    db.commit()
    return get_business_detail(db, business_id)


def set_business_status(db: Session, business_id, status: str) -> Optional[dict]:
    """Manual admin override -- see AdminBusinessStatusUpdate. Suspending a
    business also drops it to the Free plan (no active paid plan while
    suspended, mirroring what a real failed-payment webhook would do once
    billing is wired up -- see files/FEATURES.md's "not yet built" list).
    Reactivating only flips status back; the admin/business sets a plan
    separately afterward, since we have no record of what to restore it to."""
    business = db.query(Business).filter(Business.id == business_id).first()
    if not business:
        return None

    business.status = status
    if status == "suspended":
        business.plan = "free"
        business.api_access_addon = False

    db.commit()
    return get_business_detail(db, business_id)


def get_business_detail(db: Session, business_id) -> Optional[dict]:
    business = db.query(Business).filter(Business.id == business_id).first()
    if not business:
        return None

    settings_row = db.query(BusinessSettings).filter(BusinessSettings.business_id == business.id).first()
    owners = db.query(User).filter(User.business_id == business.id).order_by(User.created_at).all()
    plan_status = plan_service.get_plan_status(db, business)

    faqs = db.query(func.count(FAQ.id)).filter(FAQ.business_id == business.id).scalar() or 0
    leads = db.query(func.count(Lead.id)).filter(Lead.business_id == business.id).scalar() or 0
    conversations_total = (
        db.query(func.count(Conversation.id)).filter(Conversation.business_id == business.id).scalar() or 0
    )

    cutoff = datetime.now(timezone.utc) - timedelta(days=30)

    return {
        "id": business.id,
        "name": business.name,
        "slug": business.slug,
        "industry": business.industry,
        "logo_url": business.logo_url,
        "primary_color": business.primary_color,
        "plan": business.plan,
        "plan_name": get_plan(business.plan).name,
        "status": business.status,
        "api_access_addon": bool(business.api_access_addon),
        "created_at": business.created_at,
        "updated_at": business.updated_at,
        "settings": {
            "tone": settings_row.tone,
            "llm_provider": settings_row.llm_provider,
            "llm_model": settings_row.llm_model,
            "languages": settings_row.languages,
            "contact_email": settings_row.contact_email,
            "contact_phone": settings_row.contact_phone,
        } if settings_row else None,
        "owners": owners,
        "plan_limits": plan_status["limits"],
        "usage": plan_status["usage"],
        "features": plan_status["features"],
        "faqs": faqs,
        "leads": leads,
        "conversations_total": conversations_total,
        "llm_usage_30d": _llm_usage_summary(db, business.id, cutoff),
    }


def get_platform_overview(db: Session) -> dict:
    total = db.query(func.count(Business.id)).scalar() or 0

    businesses_by_plan = {p: c for p, c in db.query(Business.plan, func.count(Business.id)).group_by(Business.plan).all()}
    businesses_by_status = {
        s: c for s, c in db.query(Business.status, func.count(Business.id)).group_by(Business.status).all()
    }

    cutoff = datetime.now(timezone.utc) - timedelta(days=30)
    day_rows = (
        db.query(func.date(Business.created_at), func.count(Business.id))
        .filter(Business.created_at >= cutoff)
        .group_by(func.date(Business.created_at))
        .order_by(func.date(Business.created_at))
        .all()
    )
    signups_last_30d = [{"date": str(d), "count": c} for d, c in day_rows]

    return {
        "total_businesses": total,
        "businesses_by_plan": businesses_by_plan,
        "businesses_by_status": businesses_by_status,
        "signups_last_30d": signups_last_30d,
        "total_conversations": db.query(func.count(Conversation.id)).scalar() or 0,
        "total_leads": db.query(func.count(Lead.id)).scalar() or 0,
        "total_documents": db.query(func.count(Document.id)).scalar() or 0,
    }


def get_llm_usage(db: Session, business_id: Optional[str] = None, days: int = 30) -> dict:
    cutoff = datetime.now(timezone.utc) - timedelta(days=days)
    base = db.query(LLMUsageLog).filter(LLMUsageLog.provider == "groq", LLMUsageLog.created_at >= cutoff)
    if business_id:
        base = base.filter(LLMUsageLog.business_id == business_id)

    requests, prompt_tokens, completion_tokens, total_tokens = base.with_entities(
        func.count(LLMUsageLog.id),
        func.coalesce(func.sum(LLMUsageLog.prompt_tokens), 0),
        func.coalesce(func.sum(LLMUsageLog.completion_tokens), 0),
        func.coalesce(func.sum(LLMUsageLog.total_tokens), 0),
    ).first()

    day_rows = (
        base.with_entities(
            func.date(LLMUsageLog.created_at),
            func.count(LLMUsageLog.id),
            func.coalesce(func.sum(LLMUsageLog.total_tokens), 0),
        )
        .group_by(func.date(LLMUsageLog.created_at))
        .order_by(func.date(LLMUsageLog.created_at))
        .all()
    )
    by_day = [{"date": str(d), "requests": r, "total_tokens": t} for d, r, t in day_rows]

    business_rows = (
        base.join(Business, Business.id == LLMUsageLog.business_id)
        .with_entities(
            LLMUsageLog.business_id,
            Business.name,
            func.count(LLMUsageLog.id),
            func.coalesce(func.sum(LLMUsageLog.total_tokens), 0),
        )
        .group_by(LLMUsageLog.business_id, Business.name)
        .order_by(func.coalesce(func.sum(LLMUsageLog.total_tokens), 0).desc())
        .limit(10)
        .all()
    )
    by_business = [
        {"business_id": bid, "business_name": name, "requests": r, "total_tokens": t}
        for bid, name, r, t in business_rows
    ]

    return {
        "totals": {
            "requests": requests or 0,
            "prompt_tokens": prompt_tokens or 0,
            "completion_tokens": completion_tokens or 0,
            "total_tokens": total_tokens or 0,
        },
        "by_day": by_day,
        "by_business": by_business,
    }
