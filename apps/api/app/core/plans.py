"""Single source of truth for pricing plans.

Every limit/feature check in the app (documents, products, conversations,
websites, analytics tier, custom branding, notification channels, API
access, ...) reads from PLANS instead of hardcoding numbers, so changing a
price or cap means editing this file only.

`None` on a limit means "unlimited".
"""
from dataclasses import dataclass, field
from typing import Optional


@dataclass(frozen=True)
class PlanLimits:
    max_websites: Optional[int]
    max_conversations_per_month: Optional[int]
    max_document_uploads: Optional[int]
    max_products: Optional[int]
    max_languages: Optional[int]
    conversation_history_days: Optional[int]


@dataclass(frozen=True)
class PlanFeatures:
    knowledge_base: bool
    lead_capture: bool
    # "basic" | "standard" | "advanced" -- controls which analytics fields
    # analytics.py includes in the response (see plan_service.resolve_analytics_tier).
    analytics_tier: str
    email_notifications: bool
    whatsapp_notifications: bool
    instagram_integration: bool
    multi_currency: bool
    custom_branding: bool
    # Included for free as part of the plan (Growth). Business gets it only
    # via the paid add-on -- see Business.api_access_addon in plan_service.
    api_access: bool
    api_access_addon_available: bool
    priority_support: bool


@dataclass(frozen=True)
class Plan:
    key: str
    name: str
    price_usd: int
    tagline: str
    limits: PlanLimits
    features: PlanFeatures


# Features that exist as a flag/gate (frontend can show them as included or
# locked) but have no real backend integration yet -- there's no WhatsApp
# Business API / Meta Instagram integration wired up anywhere in this repo.
# Gating logic still runs (so upgrade/lock UI is accurate); the moment
# someone tries to *use* one, plan_service.require_feature raises 501 with
# a "coming soon" message instead of silently pretending it works.
NOT_YET_IMPLEMENTED_FEATURES = {"whatsapp_notifications", "instagram_integration"}


PLANS: dict[str, Plan] = {
    "free": Plan(
        key="free",
        name="Free",
        price_usd=0,
        tagline="Try it for real, no card required.",
        limits=PlanLimits(
            max_websites=1,
            max_conversations_per_month=50,
            max_document_uploads=2,
            max_products=10,
            max_languages=1,
            conversation_history_days=7,
        ),
        features=PlanFeatures(
            knowledge_base=True,
            lead_capture=True,
            analytics_tier="basic",
            email_notifications=True,
            whatsapp_notifications=False,
            instagram_integration=False,
            multi_currency=False,
            custom_branding=False,
            api_access=False,
            api_access_addon_available=False,
            priority_support=False,
        ),
    ),
    "basic": Plan(
        key="basic",
        name="Basic",
        price_usd=24,
        tagline="For a single business finding its footing.",
        limits=PlanLimits(
            max_websites=1,
            max_conversations_per_month=1000,
            max_document_uploads=20,
            max_products=100,
            max_languages=2,
            conversation_history_days=90,
        ),
        features=PlanFeatures(
            knowledge_base=True,
            lead_capture=True,
            analytics_tier="standard",
            email_notifications=True,
            whatsapp_notifications=False,
            instagram_integration=False,
            multi_currency=True,
            custom_branding=True,
            api_access=False,
            api_access_addon_available=False,
            priority_support=False,
        ),
    ),
    "business": Plan(
        key="business",
        name="Business",
        price_usd=48,
        tagline="Most businesses land here.",
        limits=PlanLimits(
            max_websites=3,
            max_conversations_per_month=5000,
            max_document_uploads=None,
            max_products=None,
            max_languages=None,
            conversation_history_days=None,
        ),
        features=PlanFeatures(
            knowledge_base=True,
            lead_capture=True,
            analytics_tier="advanced",
            email_notifications=True,
            whatsapp_notifications=True,
            instagram_integration=True,
            multi_currency=True,
            custom_branding=True,
            api_access=False,
            api_access_addon_available=True,  # +$12/mo add-on
            priority_support=True,
        ),
    ),
    "growth": Plan(
        key="growth",
        name="Growth",
        price_usd=96,
        tagline="For multi-location or high-traffic businesses.",
        limits=PlanLimits(
            max_websites=10,
            max_conversations_per_month=20000,
            max_document_uploads=None,
            max_products=None,
            max_languages=None,
            conversation_history_days=None,
        ),
        features=PlanFeatures(
            knowledge_base=True,
            lead_capture=True,
            analytics_tier="advanced",
            email_notifications=True,
            whatsapp_notifications=True,
            instagram_integration=True,
            multi_currency=True,
            custom_branding=True,
            api_access=True,  # included, no add-on needed
            api_access_addon_available=False,
            priority_support=True,
        ),
    ),
}

DEFAULT_PLAN_KEY = "free"


def get_plan(plan_key: Optional[str]) -> Plan:
    return PLANS.get(plan_key or DEFAULT_PLAN_KEY, PLANS[DEFAULT_PLAN_KEY])
