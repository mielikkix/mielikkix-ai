"""SEO Audit & Optimization -- audit run orchestration (apps/agents/
seo-copywriter/CLAUDE.md). Stage 2 (crawl + per-page structured extraction,
stored as SeoCrawledPage rows), Stage 3 (technical analyzer, health_
technical), Stage 4 (on-page analyzer, health_on_page), and Stage 5
(overall_health/finding_severity_counts summary) run entirely
deterministically. Stage 6 (recommendation engine) is the first LLM call
in this pipeline: a deterministic action plan built from the SeoFinding
rows already persisted, plus an LLM-written executive summary over that
same real data (see seo_recommendation_service.py). Performance/keyword
analyzers are later stages -- not run here yet.

No job queue exists in this codebase (see that CLAUDE.md's "What already
exists that this reuses") -- run_audit follows crawl_and_ingest_website's
own shape (document_service.py): a FastAPI BackgroundTasks call that opens
its own DB session, since the request's session is already closed by the
time it runs.
"""
from datetime import datetime, timezone
from typing import Optional
from urllib.robotparser import RobotFileParser

from sqlalchemy import func
from sqlalchemy.orm import Session

from ..core.database import SessionLocal
from ..models.seo_audit import SeoAudit, SeoCrawledPage, SeoFinding
from ..models.seo_website import SeoWebsite, CRAWL_TIER_PAGE_LIMITS
from . import seo_onpage_analyzer, seo_page_analyzer, seo_recommendation_service, seo_technical_analyzer, web_crawl
from .seo_finding_common import FindingDraft


def _persist_findings(db: Session, audit: SeoAudit, drafts: list[FindingDraft]) -> None:
    for draft in drafts:
        db.add(SeoFinding(
            audit_id=audit.id,
            business_id=audit.business_id,
            category=draft.category,
            rule_code=draft.rule_code,
            severity=draft.severity,
            affected_url=draft.affected_url,
            issue=draft.issue,
            explanation=draft.explanation,
            recommended_fix=draft.recommended_fix,
            evidence=draft.evidence,
        ))


def create_audit(db: Session, website: SeoWebsite) -> SeoAudit:
    audit = SeoAudit(website_id=website.id, business_id=website.business_id, status="pending")
    db.add(audit)
    db.commit()
    db.refresh(audit)
    return audit


async def run_audit(audit_id: str) -> None:
    """Background-task worker for POST .../websites/{id}/audits. Discovers
    pages up to the website's own crawl_tier cap, analyzes each with
    seo_page_analyzer, and stores one SeoCrawledPage row per page --
    a single bad page (timeout, non-HTML, blocked) is skipped and counted
    in pages_blocked rather than aborting the rest of the audit, the same
    "one bad item doesn't abort the rest" rule crawl_and_ingest_website
    already follows for document ingestion.
    """
    db = SessionLocal()
    try:
        audit = db.query(SeoAudit).filter(SeoAudit.id == audit_id).first()
        if audit is None:
            return
        website = db.query(SeoWebsite).filter(SeoWebsite.id == audit.website_id).first()
        if website is None:
            audit.status = "failed"
            db.commit()
            return

        audit.status = "running"
        audit.started_at = datetime.now(timezone.utc)
        db.commit()

        max_pages = CRAWL_TIER_PAGE_LIMITS.get(website.crawl_tier, CRAWL_TIER_PAGE_LIMITS["starter"])

        try:
            pages = await web_crawl.discover_website_pages(website.url, max_pages=max_pages)
        except Exception:
            pages = []

        audit.pages_discovered = len(pages)
        db.commit()

        crawled = 0
        blocked = 0
        crawled_pages: list[SeoCrawledPage] = []
        for page_url in pages:
            try:
                analysis = await seo_page_analyzer.analyze_page(page_url)
            except Exception:
                blocked += 1
                continue

            crawled_page = SeoCrawledPage(
                audit_id=audit.id,
                url=analysis.url,
                http_status=analysis.http_status,
                title=analysis.title,
                meta_description=analysis.meta_description,
                h1_count=analysis.h1_count,
                word_count=analysis.word_count,
                canonical_url=analysis.canonical_url,
                meta_robots=analysis.meta_robots,
                x_robots_tag=analysis.x_robots_tag,
                is_indexable=analysis.is_indexable,
                redirect_chain=analysis.redirect_chain,
                internal_link_count=analysis.internal_link_count,
                image_count=analysis.image_count,
                images_missing_alt=analysis.images_missing_alt,
                content_hash=analysis.content_hash,
            )
            db.add(crawled_page)
            crawled_pages.append(crawled_page)
            crawled += 1

        audit.pages_crawled = crawled
        audit.pages_blocked = blocked
        db.commit()

        # Stage 3: technical analyzer -- one more robots.txt fetch (raw text,
        # for the analyzer's own rules) and a dedicated sitemap fetch (the
        # raw sitemap URL list, separate from discover_website_pages' own
        # merged/robots-filtered output, so the "sitemap submits a URL
        # robots.txt blocks" conflict check has something real to compare).
        site_root = web_crawl.site_root(website.url)
        robots_txt = await web_crawl.fetch_robots_txt_text(site_root)
        robots_parser = RobotFileParser()
        robots_parser.parse(robots_txt.splitlines() if robots_txt is not None else [])
        try:
            sitemap_urls = await web_crawl.discover_sitemap_urls(site_root)
        except Exception:
            sitemap_urls = []

        technical_drafts = seo_technical_analyzer.analyze(
            crawled_pages, robots_txt, robots_parser, sitemap_urls, site_root
        )
        _persist_findings(db, audit, technical_drafts)
        audit.health_technical = seo_technical_analyzer.health_score(technical_drafts)

        # Stage 4: on-page analyzer -- titles, meta descriptions, headings,
        # thin/duplicate content, image alt text. Runs on the same
        # crawled_pages already fetched above; no additional network calls.
        onpage_drafts = seo_onpage_analyzer.analyze(crawled_pages)
        _persist_findings(db, audit, onpage_drafts)
        audit.health_on_page = seo_onpage_analyzer.health_score(onpage_drafts)
        db.commit()

        # Stage 6: recommendation engine -- the action plan is built
        # deterministically from the SeoFinding rows just persisted above
        # (real DB state, including their status); only the executive-
        # summary narrative on top of it involves an LLM call.
        all_findings = db.query(SeoFinding).filter(SeoFinding.audit_id == audit.id).all()
        action_plan = seo_recommendation_service.build_action_plan(all_findings)
        audit.executive_summary = await seo_recommendation_service.generate_executive_summary(
            overall_health(audit), finding_severity_counts(db, audit.id), action_plan
        )

        audit.status = "completed"
        audit.completed_at = datetime.now(timezone.utc)
        db.commit()
    except Exception:
        db.rollback()
        audit = db.query(SeoAudit).filter(SeoAudit.id == audit_id).first()
        if audit is not None:
            audit.status = "failed"
            audit.completed_at = datetime.now(timezone.utc)
            db.commit()
    finally:
        db.close()


def list_audits(db: Session, business_id, website_id: str) -> list[SeoAudit]:
    return (
        db.query(SeoAudit)
        .filter(SeoAudit.business_id == business_id, SeoAudit.website_id == website_id)
        .order_by(SeoAudit.created_at.desc())
        .all()
    )


def get_audit(db: Session, business_id, audit_id: str) -> Optional[SeoAudit]:
    return db.query(SeoAudit).filter(SeoAudit.id == audit_id, SeoAudit.business_id == business_id).first()


def list_crawled_pages(db: Session, audit_id: str) -> list[SeoCrawledPage]:
    return (
        db.query(SeoCrawledPage)
        .filter(SeoCrawledPage.audit_id == audit_id)
        .order_by(SeoCrawledPage.created_at)
        .all()
    )


_SEVERITY_ORDER = {"critical": 0, "high": 1, "medium": 2, "low": 3, "informational": 4}

HEALTH_CATEGORIES = ["health_technical", "health_on_page", "health_performance", "health_content", "health_internal_linking"]


def finding_severity_counts(db: Session, audit_id: str) -> dict[str, int]:
    """Total findings by severity for one audit -- Stage 5's "SEO Health"
    overview (apps/agents/seo-copywriter/CLAUDE.md, Phase 10). Always
    real counts from stored SeoFinding rows, never estimated."""
    counts = {key: 0 for key in _SEVERITY_ORDER}
    rows = (
        db.query(SeoFinding.severity, func.count(SeoFinding.id))
        .filter(SeoFinding.audit_id == audit_id)
        .group_by(SeoFinding.severity)
        .all()
    )
    for severity, count in rows:
        counts[severity] = count
    return counts


def overall_health(audit: SeoAudit) -> Optional[int]:
    """Average of whichever category scores have actually been computed
    so far, rounded -- an internal diagnostic composite, explicitly never
    presented as a real Google ranking score (this agent's CLAUDE.md,
    Phase 10). None (not 0, not a guess) until at least one category has
    run, and only averages categories that exist -- a website that hasn't
    had its performance/content/internal-linking passes run yet isn't
    penalized for scores that were never computed."""
    scores = [getattr(audit, key) for key in HEALTH_CATEGORIES if getattr(audit, key) is not None]
    if not scores:
        return None
    return round(sum(scores) / len(scores))


def list_findings(
    db: Session,
    business_id,
    audit_id: str,
    category: Optional[str] = None,
    severity: Optional[str] = None,
    status: Optional[str] = None,
) -> list[SeoFinding]:
    query = db.query(SeoFinding).filter(SeoFinding.audit_id == audit_id, SeoFinding.business_id == business_id)
    if category:
        query = query.filter(SeoFinding.category == category)
    if severity:
        query = query.filter(SeoFinding.severity == severity)
    if status:
        query = query.filter(SeoFinding.status == status)
    findings = query.all()
    # Most severe first -- created_at as a stable tiebreaker so the order
    # doesn't shuffle between requests for findings of the same severity.
    return sorted(findings, key=lambda f: (_SEVERITY_ORDER.get(f.severity, 99), f.created_at))


def update_finding_status(db: Session, business_id, finding_id: str, status: str) -> Optional[SeoFinding]:
    finding = (
        db.query(SeoFinding)
        .filter(SeoFinding.id == finding_id, SeoFinding.business_id == business_id)
        .first()
    )
    if finding is None:
        return None
    finding.status = status
    db.commit()
    db.refresh(finding)
    return finding


def get_action_plan(db: Session, business_id, audit_id: str) -> list:
    """Stage 6's prioritized action plan (see seo_recommendation_service.
    build_action_plan) -- built fresh from the audit's current SeoFinding
    rows on every call rather than persisted, so an "Ignore"d finding
    (updated via update_finding_status) is reflected the moment the plan
    is viewed again, with no separate cache to invalidate."""
    findings = db.query(SeoFinding).filter(SeoFinding.audit_id == audit_id, SeoFinding.business_id == business_id).all()
    return seo_recommendation_service.build_action_plan(findings)
