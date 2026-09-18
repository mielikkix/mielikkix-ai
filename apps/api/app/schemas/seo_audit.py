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
        )
