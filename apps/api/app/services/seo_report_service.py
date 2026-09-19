"""SEO Audit & Optimization -- Stage 11 (apps/agents/seo-copywriter/
CLAUDE.md, Phase 17): a single client-presentable rollup of one completed
audit.

Entirely deterministic and does no new analysis or LLM call of its own --
it just assembles data already computed by earlier stages (website
identity, the audit's own health scores, its Stage 6 executive summary,
top action-plan items, real finding counts, keyword-opportunity count)
into one structure meant to be shown to (or shared with) the tenant's own
client. Per this agent's CLAUDE.md, PDF export is deliberately NOT
implemented here -- this stage only builds the structured report data plus
a dashboard view; a PDF renderer can consume this exact same structure
later without any service-layer change.
"""
from dataclasses import dataclass
from typing import List

from sqlalchemy.orm import Session

from ..models.seo_audit import SeoAudit
from ..models.seo_website import SeoWebsite
from . import seo_audit_service
from .seo_recommendation_service import ActionPlanItem

DEFAULT_TOP_ACTION_ITEMS = 5


class ReportNotReadyError(Exception):
    """Raised when a report is requested for an audit that hasn't
    completed yet -- a client-facing report over a partial or failed run
    would show misleading, incomplete data."""


@dataclass
class SeoReport:
    website: SeoWebsite
    audit: SeoAudit
    overall_health: int | None
    finding_counts: dict
    top_action_items: List[ActionPlanItem]
    keyword_opportunity_count: int


def build_report(db: Session, business_id, audit_id: str, top_n: int = DEFAULT_TOP_ACTION_ITEMS) -> SeoReport:
    audit = seo_audit_service.get_audit(db, business_id, audit_id)
    if audit is None:
        raise ValueError("Audit not found.")
    if audit.status != "completed":
        raise ReportNotReadyError("This audit hasn't completed yet -- a report needs a finished run.")

    website = db.query(SeoWebsite).filter(SeoWebsite.id == audit.website_id).first()
    action_plan = seo_audit_service.get_action_plan(db, business_id, audit_id)
    keyword_opportunities = seo_audit_service.list_keyword_opportunities(db, business_id, audit_id)

    return SeoReport(
        website=website,
        audit=audit,
        overall_health=seo_audit_service.overall_health(audit),
        finding_counts=seo_audit_service.finding_severity_counts(db, audit_id),
        top_action_items=action_plan[:top_n],
        keyword_opportunity_count=len(keyword_opportunities),
    )
