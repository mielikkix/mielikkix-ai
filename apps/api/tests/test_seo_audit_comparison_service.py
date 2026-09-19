"""Tests for Stage 10 (apps/agents/seo-copywriter/CLAUDE.md, Phase 16):
comparing two audits of the same website. Entirely deterministic -- no LLM
involved -- so these tests build real SeoAudit/SeoFinding rows directly and
assert on compare_audits' own matching/diff logic. HTTP wiring is covered
by test_seo_audit_comparison_integration.py.
"""
import pytest

from app.models.seo_audit import SeoAudit, SeoFinding
from app.models.seo_website import SeoWebsite
from app.services import seo_audit_comparison_service as sacs


def _website(business):
    return SeoWebsite(business_id=business["business_id"], url="https://greenleaf.test", crawl_tier="starter")


def _audit(business, website, **overrides):
    defaults = dict(website_id=website.id, business_id=business["business_id"], status="completed")
    defaults.update(overrides)
    return SeoAudit(**defaults)


def _finding(audit, business, **overrides):
    defaults = dict(
        audit_id=audit.id, business_id=business["business_id"], category="on_page",
        rule_code="missing_title", severity="high", issue="Missing title", affected_url="https://greenleaf.test/",
    )
    defaults.update(overrides)
    return SeoFinding(**defaults)


def test_resolved_finding_present_in_previous_but_not_current(db_session, business):
    website = _website(business)
    db_session.add(website)
    db_session.commit()

    previous = _audit(business, website, health_on_page=60)
    db_session.add(previous)
    db_session.commit()
    db_session.add(_finding(previous, business, rule_code="missing_title"))
    db_session.commit()

    current = _audit(business, website, health_on_page=90)
    db_session.add(current)
    db_session.commit()

    comparison = sacs.compare_audits(db_session, business["business_id"], str(previous.id), str(current.id))

    assert len(comparison.resolved_findings) == 1
    assert comparison.resolved_findings[0].rule_code == "missing_title"
    assert comparison.new_findings == []
    assert comparison.persisting_findings == []
    assert comparison.overall_health_delta == 30


def test_new_finding_present_in_current_but_not_previous(db_session, business):
    website = _website(business)
    db_session.add(website)
    db_session.commit()

    previous = _audit(business, website)
    db_session.add(previous)
    db_session.commit()

    current = _audit(business, website)
    db_session.add(current)
    db_session.commit()
    db_session.add(_finding(current, business, rule_code="thin_content"))
    db_session.commit()

    comparison = sacs.compare_audits(db_session, business["business_id"], str(previous.id), str(current.id))

    assert comparison.resolved_findings == []
    assert len(comparison.new_findings) == 1
    assert comparison.new_findings[0].rule_code == "thin_content"


def test_persisting_finding_present_in_both_by_rule_code_and_url(db_session, business):
    website = _website(business)
    db_session.add(website)
    db_session.commit()

    previous = _audit(business, website)
    db_session.add(previous)
    db_session.commit()
    db_session.add(_finding(previous, business, rule_code="missing_title", affected_url="https://greenleaf.test/a"))
    db_session.commit()

    current = _audit(business, website)
    db_session.add(current)
    db_session.commit()
    db_session.add(_finding(current, business, rule_code="missing_title", affected_url="https://greenleaf.test/a"))
    db_session.commit()

    comparison = sacs.compare_audits(db_session, business["business_id"], str(previous.id), str(current.id))

    assert comparison.resolved_findings == []
    assert comparison.new_findings == []
    assert len(comparison.persisting_findings) == 1


def test_same_rule_code_different_url_is_not_a_match(db_session, business):
    """Fixing the issue on page A while it's still broken on page B should
    show as one resolved + one new, not one persisting -- affected_url is
    part of the match key."""
    website = _website(business)
    db_session.add(website)
    db_session.commit()

    previous = _audit(business, website)
    db_session.add(previous)
    db_session.commit()
    db_session.add(_finding(previous, business, rule_code="missing_title", affected_url="https://greenleaf.test/a"))
    db_session.commit()

    current = _audit(business, website)
    db_session.add(current)
    db_session.commit()
    db_session.add(_finding(current, business, rule_code="missing_title", affected_url="https://greenleaf.test/b"))
    db_session.commit()

    comparison = sacs.compare_audits(db_session, business["business_id"], str(previous.id), str(current.id))

    assert len(comparison.resolved_findings) == 1
    assert len(comparison.new_findings) == 1
    assert comparison.persisting_findings == []


def test_site_wide_finding_with_no_url_matches_by_rule_code_alone(db_session, business):
    website = _website(business)
    db_session.add(website)
    db_session.commit()

    previous = _audit(business, website)
    db_session.add(previous)
    db_session.commit()
    db_session.add(_finding(previous, business, rule_code="missing_sitemap", affected_url=None, category="technical"))
    db_session.commit()

    current = _audit(business, website)
    db_session.add(current)
    db_session.commit()
    db_session.add(_finding(current, business, rule_code="missing_sitemap", affected_url=None, category="technical"))
    db_session.commit()

    comparison = sacs.compare_audits(db_session, business["business_id"], str(previous.id), str(current.id))

    assert len(comparison.persisting_findings) == 1


def test_order_of_audit_ids_passed_in_does_not_matter(db_session, business):
    """compare_audits orders by created_at internally -- passing the newer
    audit's ID first must produce the identical result as passing it
    second."""
    website = _website(business)
    db_session.add(website)
    db_session.commit()

    previous = _audit(business, website, health_technical=50)
    db_session.add(previous)
    db_session.commit()

    current = _audit(business, website, health_technical=80)
    db_session.add(current)
    db_session.commit()

    forward = sacs.compare_audits(db_session, business["business_id"], str(previous.id), str(current.id))
    backward = sacs.compare_audits(db_session, business["business_id"], str(current.id), str(previous.id))

    assert forward.previous_audit.id == backward.previous_audit.id == previous.id
    assert forward.current_audit.id == backward.current_audit.id == current.id
    assert forward.overall_health_delta == backward.overall_health_delta == 30


def test_health_delta_is_none_when_either_side_has_no_score_yet(db_session, business):
    website = _website(business)
    db_session.add(website)
    db_session.commit()

    previous = _audit(business, website)  # no health_* set at all
    db_session.add(previous)
    db_session.commit()

    current = _audit(business, website, health_technical=80)
    db_session.add(current)
    db_session.commit()

    comparison = sacs.compare_audits(db_session, business["business_id"], str(previous.id), str(current.id))

    assert comparison.overall_health_previous is None
    assert comparison.overall_health_current == 80
    assert comparison.overall_health_delta is None


def test_unknown_audit_id_raises_value_error(db_session, business):
    website = _website(business)
    db_session.add(website)
    db_session.commit()
    audit = _audit(business, website)
    db_session.add(audit)
    db_session.commit()

    with pytest.raises(ValueError):
        sacs.compare_audits(db_session, business["business_id"], str(audit.id), "00000000-0000-0000-0000-000000000000")


def test_comparing_audits_from_different_websites_raises_comparison_error(db_session, business):
    website_a = SeoWebsite(business_id=business["business_id"], url="https://a.test", crawl_tier="starter")
    website_b = SeoWebsite(business_id=business["business_id"], url="https://b.test", crawl_tier="starter")
    db_session.add_all([website_a, website_b])
    db_session.commit()

    audit_a = _audit(business, website_a)
    audit_b = _audit(business, website_b)
    db_session.add_all([audit_a, audit_b])
    db_session.commit()

    with pytest.raises(sacs.AuditComparisonError):
        sacs.compare_audits(db_session, business["business_id"], str(audit_a.id), str(audit_b.id))


def test_comparing_an_audit_to_itself_raises_comparison_error(db_session, business):
    website = _website(business)
    db_session.add(website)
    db_session.commit()
    audit = _audit(business, website)
    db_session.add(audit)
    db_session.commit()

    with pytest.raises(sacs.AuditComparisonError):
        sacs.compare_audits(db_session, business["business_id"], str(audit.id), str(audit.id))


def test_cannot_compare_another_businesss_audit(db_session, business):
    """business_id scoping means an audit belonging to another business
    simply doesn't resolve -- same "not found" behavior as an unknown ID,
    never a cross-tenant leak."""
    website = _website(business)
    db_session.add(website)
    db_session.commit()
    audit = _audit(business, website)
    db_session.add(audit)
    db_session.commit()

    with pytest.raises(ValueError):
        sacs.compare_audits(db_session, "00000000-0000-0000-0000-000000000000", str(audit.id), str(audit.id))
