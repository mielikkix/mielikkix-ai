"""Registered widget websites (BusinessWebsite), counted against the plan's
website limit."""

import logging
from typing import Optional
from urllib.parse import urlparse

from sqlalchemy.orm import Session

from ..core.plans import get_plan
from ..models.business import Business
from ..models.website import BusinessWebsite

logger = logging.getLogger(__name__)

# Never auto-registered: local development, and our own dashboard (its widget preview).
_IGNORED_HOSTS = {"localhost", "127.0.0.1", "::1", "app.mielikkix.ai"}


def normalize_domain(value: str) -> str:
    """"https://www.Example.com/page/" -> "example.com". One site, one entry --
    QA 2026-10-02 (D8) found the same site twice as "https://mielikkix.ai/" and
    "https://mielikkix.ai"."""
    value = (value or "").strip().lower()
    if "://" not in value:
        value = "//" + value
    host = urlparse(value).hostname or ""
    return host[4:] if host.startswith("www.") else host


def find(db: Session, business_id, domain: str) -> Optional[BusinessWebsite]:
    wanted = normalize_domain(domain)
    for site in db.query(BusinessWebsite).filter(BusinessWebsite.business_id == business_id).all():
        if normalize_domain(site.domain) == wanted:
            return site
    return None


def register_from_origin(db: Session, business: Business, origin: Optional[str]) -> None:
    """Records the site a widget conversation came from (the browser's Origin
    header), so "Websites: 0 / 3" can't show while the widget runs on a real
    site (QA 2026-10-02, D3/M4). Best effort: skipped for local/our own hosts
    and when the plan's limit is reached -- it never blocks a chat."""
    domain = normalize_domain(origin or "")
    if not domain or domain in _IGNORED_HOSTS or domain.endswith(".localhost"):
        return
    if find(db, business.id, domain):
        return
    limit = get_plan(business.plan).limits.max_websites
    count = db.query(BusinessWebsite).filter(BusinessWebsite.business_id == business.id).count()
    if limit is not None and count >= limit:
        logger.info("widget_site_over_limit business_id=%s domain=%s", business.id, domain)
        return
    db.add(BusinessWebsite(business_id=business.id, domain=domain, label="Detected from your chat widget"))
