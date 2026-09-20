"""Catalog for the Mielikkix Force agents, sold as standalone products --
deliberately independent of the chat-widget plan tiers in plans.py. A
business's plan (Free/Basic/Business/Growth) says nothing about which
agents it has; every agent is purchased separately (individually, as a
3-pack, or as the Full Crew -- all of them). See
apps/api/app/services/agent_access_service.py for the actual entitlement
check, and apps/agents/seo-audit/CLAUDE.md's "Standalone agent
billing" decision for why this replaced the old
PlanFeatures.*_enabled booleans.

No payment processor is wired up anywhere in this app yet (same as
plans.py's paid tiers) -- prices below are placeholders, kept in one place
so correcting them later is a one-line change here, not a hunt across the
codebase.
"""
from dataclasses import dataclass


@dataclass(frozen=True)
class AgentTier:
    """One purchasable tier of an agent that's sold as free-vs-paid rather
    than a single flat price (currently just SEO Audit & Optimization --
    see agent_catalog.py's AGENTS entry below). The entitlement check itself
    stays a single on/off gate (agent_access_service.require_agent_access,
    keyed on the parent AgentProduct.key) -- tiers are a pricing/feature-copy
    distinction for the catalog UI, not a second gate, so upgrading a
    business from free to paid never needs its own new permission check."""

    key: str
    name: str
    tagline: str
    price_usd: int  # 0 for the free tier
    # Set only for a tier priced in NOK instead of USD (see the "kr" price on
    # the Professional tier below) -- None means "use price_usd" like every
    # other placeholder price in this file.
    price_nok: int | None
    # Marketing copy for the pricing card. An entry ending in "(coming soon)"
    # is NOT implemented yet -- same convention PlanPage.tsx already uses for
    # chat-widget PlanFeatures that are sold but not wired up (WhatsApp
    # notifications, Instagram integration). Never drop that suffix from an
    # item until it's actually built -- this repo's "no fabricated findings"
    # rule (apps/agents/seo-audit/CLAUDE.md) applies to sales copy too.
    features: tuple[str, ...]


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
    # Set only for an agent sold as free-vs-paid tiers instead of one flat
    # price (see AgentTier above). None for every other agent -- price_usd
    # above is still what's shown for those.
    tiers: tuple[AgentTier, ...] | None = None


AGENTS: dict[str, AgentProduct] = {
    "voice_receptionist": AgentProduct("voice_receptionist", "Voice Receptionist", 79, multi_tenant=False),
    "booking_assistant": AgentProduct("booking_assistant", "Booking Assistant", 49, multi_tenant=True),
    "support_triage": AgentProduct("support_triage", "Support Triage", 49, multi_tenant=False),
    "seo_audit_optimization": AgentProduct(
        "seo_audit_optimization",
        "SEO Audit & Optimization",
        0,
        multi_tenant=True,
        tiers=(
            AgentTier(
                key="free",
                name="SEO Audit & Optimize",
                tagline="Everything you need to start improving your site's SEO.",
                price_usd=0,
                price_nok=0,
                features=(
                    "Website crawl (starter/standard/advanced -- up to 500 pages)",
                    "Technical, on-page, and internal-linking findings",
                    "Core Web Vitals / PageSpeed Insights (needs GOOGLE_PAGESPEED_API_KEY -- "
                    "shows \"Not measured\" without one)",
                    "Prioritized action plan",
                    "AI-written executive summary",
                    "Keyword opportunity ideas",
                    "Audit history & comparison",
                    "Client-ready report with PDF export",
                    "Unlimited re-audits on your registered websites",
                ),
            ),
            AgentTier(
                key="professional",
                name="Professional SEO Audit & Optimization",
                tagline="For larger, more complex websites that need deeper crawls and integrations.",
                price_usd=0,
                price_nok=29901,
                features=(
                    "Everything in SEO Audit & Optimize, plus:",
                    "Up to 500 pages crawled per audit (current maximum)",
                    "Scheduled recurring audits (coming soon)",
                    "Custom crawl configuration (coming soon)",
                    "Save & reopen past crawls (coming soon)",
                    "JavaScript rendering (coming soon)",
                    "Near-duplicate content detection (coming soon)",
                    "Custom robots.txt testing (coming soon)",
                    "Mobile usability checks (coming soon)",
                    "AMP crawling & validation (coming soon)",
                    "Structured data validation (coming soon)",
                    "Spelling & grammar checks (coming soon)",
                    "Custom source code search (coming soon)",
                    "Custom extraction (coming soon)",
                    "Custom JavaScript (coming soon)",
                    "Crawl with OpenAI & Gemini (coming soon)",
                    "Google Analytics integration (coming soon)",
                    "Search Console integration (coming soon)",
                    "Accessibility auditing (coming soon)",
                    "Link metrics integration (coming soon)",
                    "Forms-based authentication (coming soon)",
                    "Segmentation (coming soon)",
                    "Looker Studio crawl report (coming soon)",
                    "Priority technical support (coming soon)",
                ),
            ),
        ),
    ),
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
