from typing import Dict
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from ..core.database import get_db
from ..core.dependencies import get_current_user, get_current_business, is_platform_admin
from ..models.user import User
from ..models.business import Business, BusinessSettings
from ..schemas.business import (
    BusinessOut,
    BusinessUpdate,
    BusinessSettingsOut,
    BusinessSettingsUpdate,
    PublicBusinessSettingsOut,
)
from ..schemas.plan import (
    PlanCatalogEntry,
    PlanStatusOut,
    PlanSelectRequest,
    ApiAccessAddonRequest,
    ApiKeyOut,
    NotificationChannelRequest,
)
from ..schemas.agent_access import AgentProductOut, AgentTierOut
from ..core.plans import PLANS
from ..core.agent_catalog import AGENTS
from ..services import agent_access_service, plan_service
from ..rag.providers import get_llm_provider
from ..rag.providers.base import LANGUAGE_NAMES
from ..rag.pipeline import log_llm_usage
from ..services.chat_defaults import DEFAULT_FALLBACK_MESSAGE, DEFAULT_WELCOME_MESSAGE, default_translation
import secrets
from fastapi import HTTPException

router = APIRouter(prefix="/api/businesses", tags=["businesses"])

DEFAULT_PRIMARY_COLOR = "#ff6b00"


@router.get("/{business_id}/public-settings", response_model=PublicBusinessSettingsOut)
def get_public_settings(business_id: str, db: Session = Depends(get_db)):
    # Public, widget-facing: only ever exposes display-safe fields (no contact
    # info, no LLM provider/model, nothing tenant-sensitive).
    s = db.query(BusinessSettings).filter(BusinessSettings.business_id == business_id).first()
    welcome_message = s.welcome_message if s and s.welcome_message else DEFAULT_WELCOME_MESSAGE
    languages = (s.languages if s and s.languages else None) or ["en"]
    business = db.query(Business).filter(Business.id == business_id).first()
    primary_color = business.primary_color if business and business.primary_color else DEFAULT_PRIMARY_COLOR
    return PublicBusinessSettingsOut(
        welcome_message=welcome_message,
        welcome_messages={k: v for k, v in ((s.welcome_messages if s else None) or {}).items() if v},
        languages=languages,
        primary_color=primary_color,
        privacy_policy_url=s.privacy_policy_url if s else None,
        require_chat_consent=bool(s.require_chat_consent) if s else False,
    )


async def _fill_missing_translations(db: Session, s: BusinessSettings) -> None:
    """Best-effort: every enabled language after the primary one gets a
    translated fallback reply and greeting via the configured LLM provider,
    unless it already has one (an owner-written one, or a "" the owner left
    blank on purpose -- only absent keys are filled). Fills ALL missing ones,
    not just newly added languages: a language whose translation once failed
    (no API key at the time) or that predates welcome_messages would
    otherwise stay untranslated forever and reply in the wrong language.
    See the "Fallback message (X)" / "Welcome message (X)" fields in Settings."""
    languages = s.languages or ["en"]
    targets = languages[1:]
    if not targets:
        return
    sources = {
        "fallback_messages": s.fallback_message or DEFAULT_FALLBACK_MESSAGE,
        "welcome_messages": s.welcome_message or DEFAULT_WELCOME_MESSAGE,
    }
    provider = None
    for field, source_text in sources.items():
        messages = dict(getattr(s, field) or {})
        missing = [code for code in targets if code not in messages]
        if not missing:
            continue
        for code in missing:
            builtin = default_translation(source_text, code)
            if builtin:
                messages[code] = builtin
                continue
            target_language = LANGUAGE_NAMES.get(code, code)
            provider = provider or get_llm_provider(s.llm_provider, s.llm_model)
            try:
                messages[code] = await provider.translate(source_text, target_language)
                log_llm_usage(db, s.business_id, s.llm_provider, provider, kind="translate")
            except Exception:
                # No API key configured, provider unreachable, etc. -- leave it
                # unset rather than fail the whole save; the owner can still
                # write their own translation by hand.
                pass
        setattr(s, field, messages)


@router.get("/me", response_model=BusinessOut)
def get_my_business(current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    business = db.query(Business).filter(Business.id == current_user.business_id).first()
    if not business:
        raise HTTPException(status_code=404, detail="Business not found")
    return business


@router.patch("/me", response_model=BusinessOut)
def update_my_business(
    update: BusinessUpdate,
    current_user: User = Depends(get_current_user),
    business: Business = Depends(get_current_business),
    db: Session = Depends(get_db),
):
    updates = update.model_dump(exclude_none=True)
    # Custom branding (a non-default widget color) is a paid-plan feature --
    # Free stays on the default brand color.
    if "primary_color" in updates:
        wants_custom_color = updates["primary_color"].lower() != DEFAULT_PRIMARY_COLOR.lower()
        if wants_custom_color and not plan_service.resolve_features(business)["custom_branding"]:
            raise HTTPException(
                status_code=403,
                detail="Custom branding isn't available on your plan. Upgrade to set a custom widget color.",
            )
    for field, val in updates.items():
        setattr(business, field, val)
    db.commit()
    db.refresh(business)
    return business


@router.get("/me/settings", response_model=BusinessSettingsOut)
async def get_settings(current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    s = db.query(BusinessSettings).filter(BusinessSettings.business_id == current_user.business_id).first()
    if not s:
        raise HTTPException(status_code=404, detail="Settings not found")
    # QA 2026-10-02 (D9): a language enabled before per-language greetings
    # existed (or while translation was unavailable) showed a blank Norwegian
    # welcome message though the help text says it's auto-filled. Fill what's
    # missing now -- once per language; later opens find nothing to do.
    before = (dict(s.welcome_messages or {}), dict(s.fallback_messages or {}))
    await _fill_missing_translations(db, s)
    if (dict(s.welcome_messages or {}), dict(s.fallback_messages or {})) != before:
        db.commit()
        db.refresh(s)
    return s


@router.patch("/me/settings", response_model=BusinessSettingsOut)
async def update_settings(
    update: BusinessSettingsUpdate,
    current_user: User = Depends(get_current_user),
    business: Business = Depends(get_current_business),
    db: Session = Depends(get_db),
):
    s = db.query(BusinessSettings).filter(BusinessSettings.business_id == current_user.business_id).first()
    updates = update.model_dump(exclude_none=True)
    # The AI provider/model is the platform operator's choice, not a customer
    # setting (QA 2026-10-02, D9) -- the dashboard only shows it to admins.
    if not is_platform_admin(current_user):
        for field in ("llm_provider", "llm_model"):
            if field in updates and updates[field] != getattr(s, field):
                raise HTTPException(status_code=403, detail="The AI provider is managed by Mielikkix.")
            updates.pop(field, None)
    # Retention can't be raised beyond the plan's conversation history (QA
    # 2026-10-02, M5). An existing longer value (e.g. the 90-day default on
    # Free) is kept, and lowering it is always allowed.
    history_days = plan_service.get_plan(business.plan).limits.conversation_history_days
    new_retention = updates.get("conversation_retention_days")
    if (
        new_retention is not None
        and history_days is not None
        and new_retention > max(history_days, s.conversation_retention_days or 0)
    ):
        raise HTTPException(
            status_code=403,
            detail=f"Your plan includes up to {history_days} days of conversation history. Upgrade to keep conversations longer.",
        )
    if "languages" in updates:
        plan_service.check_language_limit(business, updates["languages"])
    if updates.get("privacy_policy_url") == "":
        updates["privacy_policy_url"] = None
    for field, val in updates.items():
        setattr(s, field, val)
    if updates.keys() & {"languages", "welcome_message", "welcome_messages", "fallback_message", "fallback_messages"}:
        await _fill_missing_translations(db, s)
    db.commit()
    db.refresh(s)
    return s


# ---------------------------------------------------------------------------
# Plans
# ---------------------------------------------------------------------------

@router.get("/plans", response_model=list[PlanCatalogEntry])
def list_plans():
    """Public plan catalog -- powers the pricing/upgrade UI, no auth needed."""
    return plan_service.get_plan_catalog()


@router.get("/me/plan", response_model=PlanStatusOut)
def get_my_plan(business: Business = Depends(get_current_business), db: Session = Depends(get_db)):
    """Current plan + live usage + resolved feature flags for this business.
    This is what the dashboard reads to decide what to show/hide/lock."""
    return plan_service.get_plan_status(db, business)


@router.patch("/me/plan", response_model=PlanStatusOut)
def choose_plan(
    body: PlanSelectRequest,
    business: Business = Depends(get_current_business),
    db: Session = Depends(get_db),
):
    """Self-serve plan switching. Only ever allowed to move to Free.

    No payment processor is wired up anywhere in this app yet (frontend
    checkout is a simulated UI behind PAYMENT_COMING_SOON -- see
    PlanPage.tsx), so this endpoint must never be able to move a business
    onto a paid plan: nothing downstream of it would have verified any
    money actually changed hands. Free is safe to self-serve because it's
    the one direction with no revenue implication either way.

    Paid plans can only be set by a platform admin (`PATCH
    /api/admin/businesses/{id}/plan`, see admin_service.set_business_plan)
    until real billing exists -- that's the one place status auto-follows
    the plan today (free -> trial, paid -> active)."""
    if body.plan not in PLANS:
        raise HTTPException(status_code=400, detail=f"Unknown plan '{body.plan}'.")
    if body.plan != "free":
        raise HTTPException(
            status_code=403,
            detail=(
                "Paid plans aren't available for self-serve upgrade yet -- "
                "payment processing is coming soon. Contact us to activate a paid plan."
            ),
        )
    business.plan = "free"
    business.status = "trial"
    business.api_access_addon = False  # add-on is Business-tier only
    db.commit()
    db.refresh(business)
    return plan_service.get_plan_status(db, business)


@router.patch("/me/plan/api-access-addon", response_model=PlanStatusOut)
def set_api_access_addon(
    body: ApiAccessAddonRequest,
    business: Business = Depends(get_current_business),
    db: Session = Depends(get_db),
):
    """The discontinued Business-tier API add-on: it can still be switched
    OFF by a business that has it, but no longer newly enabled -- API access
    is sold on Growth only (QA 2026-10-02, M2)."""
    if body.enabled and not plan_service.get_plan(business.plan).features.api_access_addon_available:
        raise HTTPException(
            status_code=403,
            detail="API access is included on the Growth plan. Upgrade to Growth to use the API.",
        )
    business.api_access_addon = body.enabled
    db.commit()
    db.refresh(business)
    return plan_service.get_plan_status(db, business)


# ---------------------------------------------------------------------------
# Force agents -- sold separately from the chat-widget plan above (see
# apps/api/app/core/agent_catalog.py and apps/agents/seo-audit/
# CLAUDE.md's "Standalone agent billing" decision). No payment processor
# exists yet, same as the plan endpoints above -- activating a purchased
# agent is a platform-admin action (PATCH /api/admin/businesses/{id}/
# agents/{agent_key}, see admin_service) until real billing exists.
# ---------------------------------------------------------------------------

@router.get("/agents", response_model=list[AgentProductOut])
def list_agent_catalog():
    """Public agent catalog -- powers the "buy an agent" UI, no auth needed,
    same shape as GET /plans above."""
    return [
        AgentProductOut(
            key=a.key,
            name=a.name,
            price_nok=a.price_nok,
            multi_tenant=a.multi_tenant,
            tiers=(
                [
                    AgentTierOut(
                        key=t.key,
                        name=t.name,
                        tagline=t.tagline,
                        price_nok=t.price_nok,
                        features=list(t.features),
                    )
                    for t in a.tiers
                ]
                if a.tiers
                else None
            ),
        )
        for a in AGENTS.values()
    ]


@router.get("/me/agents", response_model=Dict[str, bool])
def get_my_agent_access(business: Business = Depends(get_current_business), db: Session = Depends(get_db)):
    """Which agents this business currently has active -- what the
    dashboard reads to decide what to show/hide/lock, replacing the old
    plan.features.*_enabled booleans this endpoint used to carry."""
    return agent_access_service.list_agent_access(db, business.id)


# ---------------------------------------------------------------------------
# API access (gated feature -- Growth includes it, Business via add-on)
# ---------------------------------------------------------------------------

@router.get("/me/api-key", response_model=ApiKeyOut)
def get_api_key(business: Business = Depends(get_current_business)):
    return ApiKeyOut(api_key=business.api_key)


@router.post("/me/api-key", response_model=ApiKeyOut)
def create_api_key(
    business: Business = Depends(get_current_business),
    db: Session = Depends(get_db),
):
    plan_service.require_feature(business, "api_access")
    business.api_key = f"an_{secrets.token_urlsafe(32)}"
    db.commit()
    db.refresh(business)
    return ApiKeyOut(api_key=business.api_key)


@router.delete("/me/api-key", response_model=ApiKeyOut)
def revoke_api_key(
    business: Business = Depends(get_current_business),
    db: Session = Depends(get_db),
):
    business.api_key = None
    db.commit()
    return ApiKeyOut(api_key=None)


# ---------------------------------------------------------------------------
# Notification channels -- WhatsApp/Instagram are plan-gated but have no
# real provider integration yet (see NOT_YET_IMPLEMENTED_FEATURES). This
# endpoint exists so the frontend has something real to call: it correctly
# returns 403 (wrong plan) or 501 (right plan, not built yet) rather than
# silently succeeding and pretending messages are being sent.
# ---------------------------------------------------------------------------

@router.post("/me/notification-channels")
def set_notification_channel(
    body: NotificationChannelRequest,
    business: Business = Depends(get_current_business),
):
    feature_key = {
        "whatsapp": "whatsapp_notifications",
        "instagram": "instagram_integration",
    }.get(body.channel)
    if not feature_key:
        raise HTTPException(status_code=400, detail=f"Unknown channel '{body.channel}'.")
    plan_service.require_feature(business, feature_key)
    return {"ok": True}  # unreachable today -- require_feature always 501s these two
