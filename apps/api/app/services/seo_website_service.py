"""SEO Audit & Optimization -- website registration. See
apps/agents/seo-copywriter/CLAUDE.md, Stage 1 ("Architecture + DB").

Uses web_crawl.assert_public_url -- the same SSRF guard (rejects private/
loopback/reserved IPs, validates scheme/host) that protects the "import my
website" document crawler, extracted to its own shared module in Stage 2
so this agent's crawler doesn't duplicate it.
"""
from fastapi import HTTPException
from sqlalchemy.orm import Session

from ..core.agent_catalog import DEFAULT_SEO_WEBSITE_LIMIT
from ..models.business import Business
from ..models.seo_website import SeoWebsite, CRAWL_TIER_PAGE_LIMITS
from . import web_crawl

VALID_CRAWL_TIERS = set(CRAWL_TIER_PAGE_LIMITS.keys())


def _website_limit(business: Business) -> int:
    return business.seo_website_limit_override or DEFAULT_SEO_WEBSITE_LIMIT


def check_website_limit(db: Session, business: Business) -> None:
    limit = _website_limit(business)
    count = db.query(SeoWebsite).filter(SeoWebsite.business_id == business.id).count()
    if count >= limit:
        raise HTTPException(
            status_code=402,
            detail=f"You've registered {limit} websites, the limit for your account. Contact us to raise it.",
        )


def create_website(
    db: Session,
    business: Business,
    url: str,
    name: str | None,
    target_country: str | None,
    target_language: str | None,
    primary_category: str | None,
    target_keywords: list[str] | None,
    crawl_tier: str,
) -> SeoWebsite:
    if crawl_tier not in VALID_CRAWL_TIERS:
        raise HTTPException(status_code=400, detail=f"crawl_tier must be one of {sorted(VALID_CRAWL_TIERS)}.")

    web_crawl.assert_public_url(url)
    check_website_limit(db, business)

    website = SeoWebsite(
        business_id=business.id,
        url=url,
        name=name,
        target_country=target_country,
        target_language=target_language,
        primary_category=primary_category,
        target_keywords=target_keywords or [],
        crawl_tier=crawl_tier,
    )
    db.add(website)
    db.commit()
    db.refresh(website)
    return website


def list_websites(db: Session, business_id) -> list[SeoWebsite]:
    return (
        db.query(SeoWebsite)
        .filter(SeoWebsite.business_id == business_id)
        .order_by(SeoWebsite.created_at.desc())
        .all()
    )


def get_website(db: Session, business_id, website_id: str) -> SeoWebsite | None:
    return (
        db.query(SeoWebsite)
        .filter(SeoWebsite.id == website_id, SeoWebsite.business_id == business_id)
        .first()
    )


def delete_website(db: Session, business_id, website_id: str) -> bool:
    website = get_website(db, business_id, website_id)
    if website is None:
        return False
    db.delete(website)
    db.commit()
    return True
