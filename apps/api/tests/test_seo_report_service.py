"""Tests for Stage 11 (apps/agents/seo-audit/CLAUDE.md, Phase 17):
the client-report rollup. Entirely deterministic -- no LLM call of its
own -- so these build real SeoAudit/SeoFinding/SeoKeywordOpportunity rows
directly. HTTP wiring is covered by test_seo_report_integration.py.
"""
import pytest

from app.models.seo_audit import SeoAudit, SeoFinding, SeoKeywordOpportunity
from app.models.seo_website import SeoWebsite
from app.services import seo_report_service as srs


def _website(business, **overrides):
    defaults = dict(business_id=business["business_id"], url="https://greenleaf.test", crawl_tier="starter")
    defaults.update(overrides)
    return SeoWebsite(**defaults)


def _audit(business, website, **overrides):
    defaults = dict(website_id=website.id, business_id=business["business_id"], status="completed")
    defaults.update(overrides)
    return SeoAudit(**defaults)


def test_report_not_found_for_unknown_audit(db_session, business):
    with pytest.raises(ValueError):
        srs.build_report(db_session, business["business_id"], "00000000-0000-0000-0000-000000000000")


def test_report_raises_when_audit_has_not_completed(db_session, business):
    website = _website(business)
    db_session.add(website)
    db_session.commit()
    audit = _audit(business, website, status="running")
    db_session.add(audit)
    db_session.commit()

    with pytest.raises(srs.ReportNotReadyError):
        srs.build_report(db_session, business["business_id"], str(audit.id))


def test_report_assembles_real_data_from_earlier_stages(db_session, business):
    website = _website(business, name="Green Leaf Cafe")
    db_session.add(website)
    db_session.commit()
    audit = _audit(business, website, health_on_page=70, health_technical=90, executive_summary="Fix the title tags first.")
    db_session.add(audit)
    db_session.commit()

    db_session.add(SeoFinding(
        audit_id=audit.id, business_id=business["business_id"], category="on_page",
        rule_code="missing_title", severity="high", issue="Missing title", affected_url="https://greenleaf.test/",
    ))
    db_session.add(SeoKeywordOpportunity(
        audit_id=audit.id, business_id=business["business_id"], keyword="organic coffee oslo", volume="Not available",
    ))
    db_session.commit()

    report = srs.build_report(db_session, business["business_id"], str(audit.id))

    assert report.website.id == website.id
    assert report.audit.id == audit.id
    assert report.overall_health == 80  # average of 70 and 90
    assert report.finding_counts["high"] == 1
    assert len(report.top_action_items) == 1
    assert report.top_action_items[0].rule_code == "missing_title"
    assert report.keyword_opportunity_count == 1


def test_report_caps_top_action_items_at_top_n(db_session, business):
    website = _website(business)
    db_session.add(website)
    db_session.commit()
    audit = _audit(business, website)
    db_session.add(audit)
    db_session.commit()

    for i in range(10):
        db_session.add(SeoFinding(
            audit_id=audit.id, business_id=business["business_id"], category="on_page",
            rule_code=f"rule_{i}", severity="high", issue=f"Issue {i}", affected_url="https://greenleaf.test/",
        ))
    db_session.commit()

    report = srs.build_report(db_session, business["business_id"], str(audit.id), top_n=3)

    assert len(report.top_action_items) == 3


def test_cannot_build_report_for_another_businesss_audit(db_session, business):
    website = _website(business)
    db_session.add(website)
    db_session.commit()
    audit = _audit(business, website)
    db_session.add(audit)
    db_session.commit()

    with pytest.raises(ValueError):
        srs.build_report(db_session, "00000000-0000-0000-0000-000000000000", str(audit.id))
