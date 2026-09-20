"""SEO Audit & Optimization -- HTTP wrapper for website registration
(Stage 1 of apps/agents/seo-audit/CLAUDE.md's staged plan). Audit
runs/findings/recommendations land in this same router in later stages;
this file only maps HTTP <-> app/services/seo_website_service.py, the same
split every other agent router in this codebase uses.

Same entitlement key as the existing SEO Copywriter routes
(app/api/agents_seo.py) -- "seo_audit_optimization" -- since the Copywriter
is being absorbed into this same agent, not sold as a second product (see
that agent's own CLAUDE.md, Phase 1).
"""
from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from sqlalchemy.orm import Session

from ..core.database import get_db
from ..core.dependencies import get_current_user, get_current_business
from ..models.business import Business
from ..models.user import User
from ..schemas.seo_website import SeoWebsiteCreate, SeoWebsiteOut
from ..schemas.seo_audit import (
    ActionPlanItemOut,
    SeoAuditComparisonOut,
    SeoAuditOut,
    SeoAuditReportOut,
    SeoCrawledPageOut,
    SeoFindingOut,
    SeoFindingStatusUpdate,
    SeoKeywordOpportunityOut,
    SeoPerformanceMeasurementOut,
)
from ..schemas.seo_draft import SeoDraftOut
from ..services import (
    agent_access_service,
    seo_audit_comparison_service,
    seo_audit_service,
    seo_report_service,
    seo_service,
    seo_website_service,
)

router = APIRouter(prefix="/api/agents/seo/websites", tags=["seo-audit"])


def _require_enabled(db: Session, business: Business) -> None:
    agent_access_service.require_agent_access(db, business, "seo_audit_optimization")


def _audit_out(db: Session, audit) -> SeoAuditOut:
    """Stage 5: every audit response carries its overall diagnostic score
    and real finding counts, not just the raw row -- see
    seo_audit_service.overall_health/finding_severity_counts."""
    return SeoAuditOut.from_orm_audit(
        audit,
        overall_health=seo_audit_service.overall_health(audit),
        finding_counts=seo_audit_service.finding_severity_counts(db, audit.id),
    )


@router.post("", response_model=SeoWebsiteOut)
def create_website(
    body: SeoWebsiteCreate,
    current_user: User = Depends(get_current_user),
    business: Business = Depends(get_current_business),
    db: Session = Depends(get_db),
):
    _require_enabled(db, business)
    website = seo_website_service.create_website(
        db,
        business,
        url=body.url,
        name=body.name,
        target_country=body.target_country,
        target_language=body.target_language,
        primary_category=body.primary_category,
        target_keywords=body.target_keywords,
        crawl_tier=body.crawl_tier,
    )
    return SeoWebsiteOut.from_orm_website(website)


@router.get("", response_model=list[SeoWebsiteOut])
def list_websites(
    current_user: User = Depends(get_current_user),
    business: Business = Depends(get_current_business),
    db: Session = Depends(get_db),
):
    _require_enabled(db, business)
    websites = seo_website_service.list_websites(db, current_user.business_id)
    return [SeoWebsiteOut.from_orm_website(w) for w in websites]


@router.get("/{website_id}", response_model=SeoWebsiteOut)
def get_website(
    website_id: str,
    current_user: User = Depends(get_current_user),
    business: Business = Depends(get_current_business),
    db: Session = Depends(get_db),
):
    _require_enabled(db, business)
    website = seo_website_service.get_website(db, current_user.business_id, website_id)
    if website is None:
        raise HTTPException(status_code=404, detail="Website not found")
    return SeoWebsiteOut.from_orm_website(website)


@router.delete("/{website_id}", status_code=204)
def delete_website(
    website_id: str,
    current_user: User = Depends(get_current_user),
    business: Business = Depends(get_current_business),
    db: Session = Depends(get_db),
):
    _require_enabled(db, business)
    deleted = seo_website_service.delete_website(db, current_user.business_id, website_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Website not found")


@router.post("/{website_id}/audits", response_model=SeoAuditOut)
def start_audit(
    website_id: str,
    background_tasks: BackgroundTasks,
    current_user: User = Depends(get_current_user),
    business: Business = Depends(get_current_business),
    db: Session = Depends(get_db),
):
    _require_enabled(db, business)
    website = seo_website_service.get_website(db, current_user.business_id, website_id)
    if website is None:
        raise HTTPException(status_code=404, detail="Website not found")

    audit = seo_audit_service.create_audit(db, website)
    background_tasks.add_task(seo_audit_service.run_audit, str(audit.id))
    return _audit_out(db, audit)


@router.get("/{website_id}/audits", response_model=list[SeoAuditOut])
def list_audits(
    website_id: str,
    current_user: User = Depends(get_current_user),
    business: Business = Depends(get_current_business),
    db: Session = Depends(get_db),
):
    _require_enabled(db, business)
    website = seo_website_service.get_website(db, current_user.business_id, website_id)
    if website is None:
        raise HTTPException(status_code=404, detail="Website not found")

    audits = seo_audit_service.list_audits(db, current_user.business_id, website_id)
    return [_audit_out(db, a) for a in audits]


audits_router = APIRouter(prefix="/api/agents/seo/audits", tags=["seo-audit"])


@audits_router.get("/{audit_id}", response_model=SeoAuditOut)
def get_audit(
    audit_id: str,
    current_user: User = Depends(get_current_user),
    business: Business = Depends(get_current_business),
    db: Session = Depends(get_db),
):
    _require_enabled(db, business)
    audit = seo_audit_service.get_audit(db, current_user.business_id, audit_id)
    if audit is None:
        raise HTTPException(status_code=404, detail="Audit not found")
    return _audit_out(db, audit)


@audits_router.get("/{audit_id}/pages", response_model=list[SeoCrawledPageOut])
def list_audit_pages(
    audit_id: str,
    current_user: User = Depends(get_current_user),
    business: Business = Depends(get_current_business),
    db: Session = Depends(get_db),
):
    _require_enabled(db, business)
    audit = seo_audit_service.get_audit(db, current_user.business_id, audit_id)
    if audit is None:
        raise HTTPException(status_code=404, detail="Audit not found")
    pages = seo_audit_service.list_crawled_pages(db, audit_id)
    return [SeoCrawledPageOut.from_orm_page(p) for p in pages]


@audits_router.get("/{audit_id}/performance", response_model=list[SeoPerformanceMeasurementOut])
def list_audit_performance(
    audit_id: str,
    current_user: User = Depends(get_current_user),
    business: Business = Depends(get_current_business),
    db: Session = Depends(get_db),
):
    """Stage 8: zero, one, or two entries (mobile/desktop) depending on
    which strategies actually got a real Core Web Vitals measurement --
    see seo_audit_service.list_performance_measurements. An empty list
    means "Not measured" for this audit, not an error."""
    _require_enabled(db, business)
    audit = seo_audit_service.get_audit(db, current_user.business_id, audit_id)
    if audit is None:
        raise HTTPException(status_code=404, detail="Audit not found")
    measurements = seo_audit_service.list_performance_measurements(db, audit_id)
    return [SeoPerformanceMeasurementOut.from_orm_measurement(m) for m in measurements]


@audits_router.get("/{audit_id}/findings", response_model=list[SeoFindingOut])
def list_findings(
    audit_id: str,
    category: str | None = None,
    severity: str | None = None,
    status: str | None = None,
    current_user: User = Depends(get_current_user),
    business: Business = Depends(get_current_business),
    db: Session = Depends(get_db),
):
    _require_enabled(db, business)
    audit = seo_audit_service.get_audit(db, current_user.business_id, audit_id)
    if audit is None:
        raise HTTPException(status_code=404, detail="Audit not found")
    findings = seo_audit_service.list_findings(
        db, current_user.business_id, audit_id, category=category, severity=severity, status=status
    )
    return [SeoFindingOut.from_orm_finding(f) for f in findings]


@audits_router.get("/{audit_id}/action-plan", response_model=list[ActionPlanItemOut])
def get_action_plan(
    audit_id: str,
    current_user: User = Depends(get_current_user),
    business: Business = Depends(get_current_business),
    db: Session = Depends(get_db),
):
    _require_enabled(db, business)
    audit = seo_audit_service.get_audit(db, current_user.business_id, audit_id)
    if audit is None:
        raise HTTPException(status_code=404, detail="Audit not found")
    items = seo_audit_service.get_action_plan(db, current_user.business_id, audit_id)
    return [ActionPlanItemOut.from_item(i) for i in items]


@audits_router.get("/{audit_id}/keyword-opportunities", response_model=list[SeoKeywordOpportunityOut])
def list_keyword_opportunities(
    audit_id: str,
    current_user: User = Depends(get_current_user),
    business: Business = Depends(get_current_business),
    db: Session = Depends(get_db),
):
    """Stage 9: LLM-suggested keyword ideas grounded in this audit's own
    crawled pages -- volume/CPC/competition always "Not available" (see
    seo_keyword_service.py). An empty list means the keyword pass found
    nothing or failed this run, not an error."""
    _require_enabled(db, business)
    audit = seo_audit_service.get_audit(db, current_user.business_id, audit_id)
    if audit is None:
        raise HTTPException(status_code=404, detail="Audit not found")
    opportunities = seo_audit_service.list_keyword_opportunities(db, current_user.business_id, audit_id)
    return [SeoKeywordOpportunityOut.from_orm_opportunity(o) for o in opportunities]


@audits_router.get("/{audit_id}/compare", response_model=SeoAuditComparisonOut)
def compare_audit(
    audit_id: str,
    against: str,
    current_user: User = Depends(get_current_user),
    business: Business = Depends(get_current_business),
    db: Session = Depends(get_db),
):
    """Stage 10: diffs `audit_id` against another audit of the SAME website
    (`against`, an audit ID) -- see seo_audit_comparison_service.py. The two
    are ordered chronologically internally, so it doesn't matter which one
    is "newer"; findings are matched across runs by (rule_code,
    affected_url), never by row ID."""
    _require_enabled(db, business)
    try:
        comparison = seo_audit_comparison_service.compare_audits(db, current_user.business_id, audit_id, against)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except seo_audit_comparison_service.AuditComparisonError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return SeoAuditComparisonOut.from_comparison(comparison)


@audits_router.get("/{audit_id}/report", response_model=SeoAuditReportOut)
def get_audit_report(
    audit_id: str,
    current_user: User = Depends(get_current_user),
    business: Business = Depends(get_current_business),
    db: Session = Depends(get_db),
):
    """Stage 11: a single client-presentable rollup of a completed audit
    (see seo_report_service.py) -- no new analysis or LLM call, just an
    assembly of data already computed by earlier stages. 400 if the audit
    hasn't completed yet (a report over a partial/failed run would show
    misleading data)."""
    _require_enabled(db, business)
    try:
        report = seo_report_service.build_report(db, current_user.business_id, audit_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except seo_report_service.ReportNotReadyError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return SeoAuditReportOut.from_report(report)


findings_router = APIRouter(prefix="/api/agents/seo/findings", tags=["seo-audit"])

_VALID_FINDING_STATUSES = {"open", "in_progress", "approved", "completed", "ignored"}


@findings_router.patch("/{finding_id}", response_model=SeoFindingOut)
def update_finding_status(
    finding_id: str,
    body: SeoFindingStatusUpdate,
    current_user: User = Depends(get_current_user),
    business: Business = Depends(get_current_business),
    db: Session = Depends(get_db),
):
    _require_enabled(db, business)
    if body.status not in _VALID_FINDING_STATUSES:
        raise HTTPException(status_code=400, detail=f"status must be one of {sorted(_VALID_FINDING_STATUSES)}.")
    finding = seo_audit_service.update_finding_status(db, current_user.business_id, finding_id, body.status)
    if finding is None:
        raise HTTPException(status_code=404, detail="Finding not found")
    return SeoFindingOut.from_orm_finding(finding)


@findings_router.get("/{finding_id}/drafts", response_model=list[SeoDraftOut])
def list_finding_drafts(
    finding_id: str,
    current_user: User = Depends(get_current_user),
    business: Business = Depends(get_current_business),
    db: Session = Depends(get_db),
):
    _require_enabled(db, business)
    drafts = seo_service.list_drafts_for_finding(db, current_user.business_id, finding_id)
    return [SeoDraftOut.from_orm_draft(d) for d in drafts]


@findings_router.post("/{finding_id}/generate-draft", response_model=SeoDraftOut)
async def generate_finding_draft(
    finding_id: str,
    current_user: User = Depends(get_current_user),
    business: Business = Depends(get_current_business),
    db: Session = Depends(get_db),
):
    """Stage 7: the Copywriter, triggered from one specific audit finding
    (see seo_service.generate_draft_for_finding) -- e.g. clicking "Generate
    Title" on a missing_title finding. Distinct from POST /api/agents/seo/
    drafts/generate (the original product-picker bulk flow, app/api/
    agents_seo.py), though both write into the same SeoDraft table and go
    through the same approve/reject endpoints there."""
    _require_enabled(db, business)
    try:
        draft = await seo_service.generate_draft_for_finding(db, str(current_user.business_id), finding_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except seo_service.UnsupportedFindingError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except seo_service.DraftGenerationError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    return SeoDraftOut.from_orm_draft(draft)
