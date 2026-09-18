"""Catalog for the Mielikkix Force agents, sold as standalone products --
deliberately independent of the chat-widget plan tiers in plans.py. A
business's plan (Free/Basic/Business/Growth) says nothing about which
agents it has; every agent is purchased separately (individually, as a
3-pack, or as the Full Crew -- all of them). See
apps/api/app/services/agent_access_service.py for the actual entitlement
check, and apps/agents/seo-copywriter/CLAUDE.md's "Standalone agent
billing" decision for why this replaced the old
PlanFeatures.*_enabled booleans.

No payment processor is wired up anywhere in this app yet (same as
plans.py's paid tiers) -- prices below are placeholders, kept in one place
so correcting them later is a one-line change here, not a hunt across the
codebase.
"""
from dataclasses import dataclass


@dataclass(frozen=True)
class AgentProduct:
    key: str
    name: str
    price_usd: int  # placeholder -- no payment processor wired up yet
    # Whether this agent's own routes actually check business_id today.
    # False means the agent (Voice Receptionist, Support Triage) is still
    # hardcoded to one business via settings.*_agent_business_id -- it has
    # no per-tenant call site to gate yet, so granting/revoking access here
    # is bookkeeping only until that agent becomes multi-tenant.
    multi_tenant: bool


AGENTS: dict[str, AgentProduct] = {
    "voice_receptionist": AgentProduct("voice_receptionist", "Voice Receptionist", 79, multi_tenant=False),
    "booking_assistant": AgentProduct("booking_assistant", "Booking Assistant", 49, multi_tenant=True),
    "support_triage": AgentProduct("support_triage", "Support Triage", 49, multi_tenant=False),
    "seo_audit_optimization": AgentProduct("seo_audit_optimization", "SEO Audit & Optimization", 59, multi_tenant=True),
    "review_reputation": AgentProduct("review_reputation", "Review & Reputation", 49, multi_tenant=True),
    "email_marketing": AgentProduct("email_marketing", "Email Marketing", 39, multi_tenant=True),
}

# Bundle pricing -- also placeholders. "Three pack"/"Full Crew" aren't
# separate database concepts: buying one is just granting several
# BusinessAgentAccess rows at once (see agent_access_service.grant_agent_access),
# so there's nothing else here to model beyond the discounted price shown
# on the purchase UI.
THREE_PACK_PRICE_USD = 129
FULL_CREW_PRICE_USD = 249

# Default cap on how many SeoWebsite rows one business may register (see
# models/seo_website.py) -- independent of any chat-widget plan limit.
# Business.seo_website_limit_override (see models/business.py) raises this
# for a specific agency-style account without touching the default for
# everyone else.
DEFAULT_SEO_WEBSITE_LIMIT = 10
