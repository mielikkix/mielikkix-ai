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
                    # Moved here from Professional 2026-09-20 (Stage 13/14,
                    # apps/agents/seo-audit/CLAUDE.md) -- both are fully
                    # built, automatic, and untiered (every audit gets them,
                    # no configuration or UI needed), so listing them as a
                    # Professional-exclusive would be inaccurate, not just
                    # unbuilt-but-promised the way "(coming soon)" items are.
                    "Structured data validation",
                    "Accessibility checks",
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
                # Authored in USD like every other price in this catalog --
                # NOT a fixed price_nok anymore (that bypassed the currency
                # switcher entirely, which was fine for a one-time
                # Norway-specific fee but broke conversion once this became
                # a normal recurring price -- confirmed live: switching to
                # EUR/USD on the pricing page did nothing). 53 USD/month is
                # the live-rate equivalent of the target 499 kr/month at the
                # time this was set (2026-09-21); it'll drift a little with
                # the exchange rate day to day, same as every other price
                # on this site already does -- that's expected, not a bug.
                price_usd=53,
                price_nok=None,  # per month (resolved 2026-09-21 -- was 29,901 kr one-time)
                # Trimmed 2026-09-20 (see apps/agents/seo-audit/CLAUDE.md's
                # "Professional tier roadmap" section) from an initial list
                # modeled 1:1 on Screaming Frog's feature table. Everything
                # removed was crawler feature-parity with Screaming Frog/
                # Ahrefs -- configurability for a technical operator this
                # agent's actual buyer (a non-expert small-business owner)
                # would never touch, and would never justify paying for when
                # those tools are free. What's left is either already in
                # progress (Stage 12: GA/Search Console) or genuinely sharpens
                # this agent's real differentiator -- AI-driven remediation
                # and business-data-informed prioritization, not raw crawler
                # power. Do not add a crawler-configurability item back here
                # without re-reading that CLAUDE.md section first.
                # Structured data validation / accessibility auditing
                # removed 2026-09-20 -- both are now built AND untiered
                # (folded into every audit's Free-tier scores), so they moved
                # to the Free tier's own list above rather than staying here
                # as a paid-exclusive. Google Analytics/Search Console
                # integration and scheduling had their "(coming soon)"
                # suffix removed 2026-09-21 once the dashboard UI to
                # self-serve connect Google (Connect Google card + property/
                # site config) and toggle scheduling (per-website dropdown)
                # actually shipped and was verified end-to-end against a
                # real account -- both are genuinely usable by a customer
                # now, not just built backend plumbing. Priority technical
                # support's "(coming soon)" removed 2026-09-21 -- a real
                # commitment to actually staff it now, not a future promise;
                # if that commitment ever lapses, put the suffix back rather
                # than leaving an unfulfillable promise (same rule as
                # everything else on this tier).
                features=(
                    "Everything in SEO Audit & Optimize, plus:",
                    "Google Analytics integration",
                    "Search Console integration",
                    "Scheduled recurring audits",
                    "Priority technical support",
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
