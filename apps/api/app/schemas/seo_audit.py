from typing import Any, Dict, List, Optional
from datetime import datetime
from pydantic import BaseModel


class SeoAuditOut(BaseModel):
    id: str
    website_id: str
    status: str
    started_at: Optional[datetime]
    completed_at: Optional[datetime]
    pages_discovered: int
    pages_crawled: int
    pages_blocked: int
    health_technical: Optional[int]
    health_on_page: Optional[int]
    health_performance: Optional[int]
    health_content: Optional[int]
    health_internal_linking: Optional[int]
    # Average of whichever health_* categories have actually been computed
    # -- an internal diagnostic composite, NOT a real Google ranking score
    # (see seo_audit_service.overall_health). None until at least one
    # category has run.
    overall_health: Optional[int]
    # Real counts of stored SeoFinding rows by severity (see
    # seo_audit_service.finding_severity_counts) -- always zero-filled for
    # every severity key, never omitted, so the UI can render a stable
    # "2 critical, 7 high, ..." summary without null-checking each key.
    finding_counts: Dict[str, int]
    # LLM-written narrative over this audit's own findings (Stage 6) --
    # null if the audit had nothing to summarize or the LLM call failed.
    # Never a fabricated placeholder.
    executive_summary: Optional[str]
    created_at: datetime

    @classmethod
    def from_orm_audit(
        cls, audit, overall_health: Optional[int] = None, finding_counts: Optional[Dict[str, int]] = None
    ) -> "SeoAuditOut":
        return cls(
            id=str(audit.id),
            website_id=str(audit.website_id),
            status=audit.status,
            started_at=audit.started_at,
            completed_at=audit.completed_at,
            pages_discovered=audit.pages_discovered,
            pages_crawled=audit.pages_crawled,
            pages_blocked=audit.pages_blocked,
            health_technical=audit.health_technical,
            health_on_page=audit.health_on_page,
            health_performance=audit.health_performance,
            health_content=audit.health_content,
            health_internal_linking=audit.health_internal_linking,
            overall_health=overall_health,
            finding_counts=finding_counts or {"critical": 0, "high": 0, "medium": 0, "low": 0, "informational": 0},
            executive_summary=audit.executive_summary,
            created_at=audit.created_at,
        )


class SeoCrawledPageOut(BaseModel):
    id: str
    url: str
    http_status: Optional[int]
    title: Optional[str]
    meta_description: Optional[str]
    h1_count: int
    word_count: int
    canonical_url: Optional[str]
    meta_robots: Optional[str]
    x_robots_tag: Optional[str]
    is_indexable: Optional[bool]
    redirect_chain: List[str]
    internal_link_count: int
    image_count: int
    images_missing_alt: int
    # Stage 13/14 (structured data + accessibility) -- see SeoCrawledPage's
    # own docstring in models/seo_audit.py for what each field means.
    structured_data_types: List[str]
    structured_data_invalid_count: int
    html_lang_present: Optional[bool]
    heading_outline: List[int]
    form_inputs_missing_label: int
    links_missing_accessible_name: int
    # Stage 12 (Google Analytics + Search Console) -- see SeoCrawledPage's
    # own docstring in models/seo_audit.py. All null = "Not measured".
    ga_sessions_28d: Optional[int]
    gsc_impressions_28d: Optional[int]
    gsc_clicks_28d: Optional[int]
    gsc_avg_position_28d: Optional[float]
    created_at: datetime

    @classmethod
    def from_orm_page(cls, page) -> "SeoCrawledPageOut":
        return cls(
            id=str(page.id),
            url=page.url,
            http_status=page.http_status,
            title=page.title,
            meta_description=page.meta_description,
            h1_count=page.h1_count,
            word_count=page.word_count,
            canonical_url=page.canonical_url,
            meta_robots=page.meta_robots,
            x_robots_tag=page.x_robots_tag,
            is_indexable=page.is_indexable,
            redirect_chain=page.redirect_chain or [],
            internal_link_count=page.internal_link_count,
            image_count=page.image_count,
            images_missing_alt=page.images_missing_alt,
            structured_data_types=page.structured_data_types or [],
            structured_data_invalid_count=page.structured_data_invalid_count,
            html_lang_present=page.html_lang_present,
            heading_outline=page.heading_outline or [],
            form_inputs_missing_label=page.form_inputs_missing_label,
            links_missing_accessible_name=page.links_missing_accessible_name,
            ga_sessions_28d=page.ga_sessions_28d,
            gsc_impressions_28d=page.gsc_impressions_28d,
            gsc_clicks_28d=page.gsc_clicks_28d,
            gsc_avg_position_28d=page.gsc_avg_position_28d,
            created_at=page.created_at,
        )


class SeoFindingOut(BaseModel):
    id: str
    audit_id: str
    category: str
    rule_code: str
    severity: str
    affected_url: Optional[str]
    issue: str
    explanation: Optional[str]
    recommended_fix: Optional[str]
    evidence: Dict[str, Any]
    status: str
    created_at: datetime

    @classmethod
    def from_orm_finding(cls, finding) -> "SeoFindingOut":
        return cls(
            id=str(finding.id),
            audit_id=str(finding.audit_id),
            category=finding.category,
            rule_code=finding.rule_code,
            severity=finding.severity,
            affected_url=finding.affected_url,
            issue=finding.issue,
            explanation=finding.explanation,
            recommended_fix=finding.recommended_fix,
            evidence=finding.evidence or {},
            status=finding.status,
            created_at=finding.created_at,
        )


class SeoFindingStatusUpdate(BaseModel):
    status: str  # "open" | "in_progress" | "approved" | "completed" | "ignored"


class ActionPlanItemOut(BaseModel):
    priority: int
    category: str
    rule_code: str
    issue: str
    affected_urls: List[str]
    why_it_matters: Optional[str]
    recommended_action: Optional[str]
    expected_benefit: str
    implementation_difficulty: str
    status: str
    # Stage 12 (Google Analytics + Search Console) -- see ActionPlanItem's
    # own docstring in seo_recommendation_service.py. None means no
    # affected URL has any real traffic data (not connected, or genuinely
    # no data yet), never a fabricated 0.
    traffic_weight: Optional[int]

    @classmethod
    def from_item(cls, item) -> "ActionPlanItemOut":
        return cls(
            priority=item.priority,
            category=item.category,
            rule_code=item.rule_code,
            issue=item.issue,
            affected_urls=item.affected_urls,
            why_it_matters=item.why_it_matters,
            recommended_action=item.recommended_action,
            expected_benefit=item.expected_benefit,
            implementation_difficulty=item.implementation_difficulty,
            status=item.status,
            traffic_weight=item.traffic_weight,
        )


class SeoPerformanceMeasurementOut(BaseModel):
    strategy: str
    performance_score: Optional[int]
    lcp_ms: Optional[int]
    cls_score: Optional[float]
    inp_ms: Optional[int]
    tbt_ms: Optional[int]
    measured_at: datetime

    @classmethod
    def from_orm_measurement(cls, measurement) -> "SeoPerformanceMeasurementOut":
        return cls(
            strategy=measurement.strategy,
            performance_score=measurement.performance_score,
            lcp_ms=measurement.lcp_ms,
            cls_score=measurement.cls,
            inp_ms=measurement.inp_ms,
            tbt_ms=measurement.tbt_ms,
            measured_at=measurement.measured_at,
        )


class SeoKeywordOpportunityOut(BaseModel):
    id: str
    keyword: str
    intent: Optional[str]
    suggested_page: Optional[str]
    current_page: Optional[str]
    content_gap: Optional[str]
    recommendation: Optional[str]
    # Always "Not available" -- no real search-volume/CPC/competition data
    # source is connected anywhere in this codebase (see
    # seo_keyword_service.py's own module docstring).
    volume: str

    @classmethod
    def from_orm_opportunity(cls, opportunity) -> "SeoKeywordOpportunityOut":
        return cls(
            id=str(opportunity.id),
            keyword=opportunity.keyword,
            intent=opportunity.intent,
            suggested_page=opportunity.suggested_page,
            current_page=opportunity.current_page,
            content_gap=opportunity.content_gap,
            recommendation=opportunity.recommendation,
            volume=opportunity.volume,
        )


class SeoAuditReportOut(BaseModel):
    website_id: str
    website_url: str
    website_name: Optional[str]
    audit_id: str
    audit_completed_at: Optional[datetime]
    # Same internal diagnostic composite as SeoAuditOut.overall_health --
    # explicitly not a real Google ranking score (see this agent's own
    # CLAUDE.md, Phase 10).
    overall_health: Optional[int]
    executive_summary: Optional[str]
    finding_counts: Dict[str, int]
    # Priority-sorted, capped at the caller's top_n (default 5) -- the
    # full list is already available via GET .../audits/{id}/action-plan.
    top_action_items: List[ActionPlanItemOut]
    keyword_opportunity_count: int

    @classmethod
    def from_report(cls, report) -> "SeoAuditReportOut":
        return cls(
            website_id=str(report.website.id),
            website_url=report.website.url,
            website_name=report.website.name,
            audit_id=str(report.audit.id),
            audit_completed_at=report.audit.completed_at,
            overall_health=report.overall_health,
            executive_summary=report.audit.executive_summary,
            finding_counts=report.finding_counts,
            top_action_items=[ActionPlanItemOut.from_item(i) for i in report.top_action_items],
            keyword_opportunity_count=report.keyword_opportunity_count,
        )


class ComparisonFindingOut(BaseModel):
    category: str
    rule_code: str
    severity: str
    affected_url: Optional[str]
    issue: str

    @classmethod
    def from_comparison_finding(cls, finding) -> "ComparisonFindingOut":
        return cls(
            category=finding.category,
            rule_code=finding.rule_code,
            severity=finding.severity,
            affected_url=finding.affected_url,
            issue=finding.issue,
        )


class SeoAuditComparisonOut(BaseModel):
    previous_audit_id: str
    current_audit_id: str
    previous_created_at: datetime
    current_created_at: datetime
    # Same internal diagnostic composite as SeoAuditOut.overall_health --
    # None if either audit hadn't computed any health category yet.
    overall_health_previous: Optional[int]
    overall_health_current: Optional[int]
    overall_health_delta: Optional[int]
    finding_counts_previous: Dict[str, int]
    finding_counts_current: Dict[str, int]
    # Matched between the two audits by (rule_code, affected_url) -- see
    # seo_audit_comparison_service.py's own docstring for why findings can't
    # be matched by ID across separate audit runs.
    resolved_findings: List[ComparisonFindingOut]
    new_findings: List[ComparisonFindingOut]
    persisting_findings: List[ComparisonFindingOut]

    @classmethod
    def from_comparison(cls, comparison) -> "SeoAuditComparisonOut":
        return cls(
            previous_audit_id=str(comparison.previous_audit.id),
            current_audit_id=str(comparison.current_audit.id),
            previous_created_at=comparison.previous_audit.created_at,
            current_created_at=comparison.current_audit.created_at,
            overall_health_previous=comparison.overall_health_previous,
            overall_health_current=comparison.overall_health_current,
            overall_health_delta=comparison.overall_health_delta,
            finding_counts_previous=comparison.finding_counts_previous,
            finding_counts_current=comparison.finding_counts_current,
            resolved_findings=[ComparisonFindingOut.from_comparison_finding(f) for f in comparison.resolved_findings],
            new_findings=[ComparisonFindingOut.from_comparison_finding(f) for f in comparison.new_findings],
            persisting_findings=[
                ComparisonFindingOut.from_comparison_finding(f) for f in comparison.persisting_findings
            ],
        )
