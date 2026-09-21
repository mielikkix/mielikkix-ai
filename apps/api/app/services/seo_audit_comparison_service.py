"""SEO Audit & Optimization -- Stage 10 (apps/agents/seo-audit/
CLAUDE.md, Phase 16): comparing two completed audits of the same website to
answer "did the fixes work / what's new / what's still broken".

Entirely deterministic -- no LLM call. SeoFinding rows don't carry a stable
identity across separate audit runs (each run persists brand-new rows), so
findings are matched between two audits by (rule_code, affected_url) --
the same issue type on the same URL (or, for a site-wide check like a
missing sitemap, the same issue type with no URL at all). A finding that
disappears between the earlier and later audit is treated as resolved; one
that's new in the later audit is treated as newly introduced (or newly
detected); one present in both is still open.
"""
from dataclasses import dataclass
from typing import Optional

from sqlalchemy.orm import Session

from ..models.seo_audit import SeoAudit, SeoFinding
from . import seo_audit_service


class AuditComparisonError(Exception):
    """Raised when two audits exist (and belong to this business) but can't
    be meaningfully compared -- different websites, or the same audit ID
    twice. Distinct from a plain ValueError (used for "audit not found"),
    so the API layer can map the two to different HTTP status codes (404
    vs. 400)."""


@dataclass
class ComparisonFinding:
    category: str
    rule_code: str
    severity: str
    affected_url: Optional[str]
    issue: str


@dataclass
class AuditComparison:
    previous_audit: SeoAudit
    current_audit: SeoAudit
    overall_health_previous: Optional[int]
    overall_health_current: Optional[int]
    overall_health_delta: Optional[int]
    finding_counts_previous: dict
    finding_counts_current: dict
    resolved_findings: list
    new_findings: list
    persisting_findings: list


def _finding_key(finding: SeoFinding) -> tuple:
    return (finding.rule_code, finding.affected_url or "")


def _to_comparison_finding(finding: SeoFinding) -> ComparisonFinding:
    return ComparisonFinding(
        category=finding.category,
        rule_code=finding.rule_code,
        severity=finding.severity,
        affected_url=finding.affected_url,
        issue=finding.issue,
    )


def compare_audits(db: Session, business_id, audit_id_a: str, audit_id_b: str) -> AuditComparison:
    """Looks up both audits (scoped to business_id, 404-equivalent via
    AuditComparisonError if either is missing), orders them chronologically
    by created_at regardless of which was passed as A/B, and diffs their
    findings. Raises AuditComparisonError if they don't belong to the same
    website -- comparing audits of two different sites has no meaning."""
    audit_a = db.query(SeoAudit).filter(SeoAudit.id == audit_id_a, SeoAudit.business_id == business_id).first()
    audit_b = db.query(SeoAudit).filter(SeoAudit.id == audit_id_b, SeoAudit.business_id == business_id).first()
    if audit_a is None or audit_b is None:
        raise ValueError("One or both audits were not found.")
    if audit_a.website_id != audit_b.website_id:
        raise AuditComparisonError("Audits belong to different websites and cannot be compared.")
    if audit_a.id == audit_b.id:
        raise AuditComparisonError("Cannot compare an audit to itself.")

    previous, current = (audit_a, audit_b) if audit_a.created_at <= audit_b.created_at else (audit_b, audit_a)

    previous_findings = db.query(SeoFinding).filter(SeoFinding.audit_id == previous.id).all()
    current_findings = db.query(SeoFinding).filter(SeoFinding.audit_id == current.id).all()

    previous_by_key = {_finding_key(f): f for f in previous_findings}
    current_by_key = {_finding_key(f): f for f in current_findings}

    resolved_keys = previous_by_key.keys() - current_by_key.keys()
    new_keys = current_by_key.keys() - previous_by_key.keys()
    persisting_keys = previous_by_key.keys() & current_by_key.keys()

    health_previous = seo_audit_service.overall_health(previous)
    health_current = seo_audit_service.overall_health(current)
    health_delta = (
        health_current - health_previous if health_previous is not None and health_current is not None else None
    )

    return AuditComparison(
        previous_audit=previous,
        current_audit=current,
        overall_health_previous=health_previous,
        overall_health_current=health_current,
        overall_health_delta=health_delta,
        finding_counts_previous=seo_audit_service.finding_severity_counts(db, previous.id),
        finding_counts_current=seo_audit_service.finding_severity_counts(db, current.id),
        resolved_findings=[_to_comparison_finding(previous_by_key[k]) for k in resolved_keys],
        new_findings=[_to_comparison_finding(current_by_key[k]) for k in new_keys],
        persisting_findings=[_to_comparison_finding(current_by_key[k]) for k in persisting_keys],
    )
