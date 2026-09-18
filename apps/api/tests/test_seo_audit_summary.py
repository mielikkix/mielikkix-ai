"""Tests for Stage 5 (apps/agents/seo-copywriter/CLAUDE.md): the audit
"SEO Health" summary -- overall_health (a composite of whichever category
scores exist) and finding_severity_counts (real counts from stored
SeoFinding rows, never estimated).
"""
from types import SimpleNamespace

from unittest.mock import AsyncMock

import pytest

from app.models.seo_audit import SeoAudit, SeoFinding
from app.models.seo_website import SeoWebsite
from app.services import seo_audit_service, seo_page_analyzer, web_crawl


def _audit(**overrides):
    defaults = dict(
        health_technical=None, health_on_page=None, health_performance=None,
        health_content=None, health_internal_linking=None,
    )
    defaults.update(overrides)
    return SimpleNamespace(**defaults)


# ---------------------------------------------------------------------------
# overall_health -- pure function
# ---------------------------------------------------------------------------

def test_overall_health_is_none_when_nothing_has_run_yet():
    assert seo_audit_service.overall_health(_audit()) is None


def test_overall_health_averages_only_computed_categories():
    audit = _audit(health_technical=80, health_on_page=60)
    assert seo_audit_service.overall_health(audit) == 70


def test_overall_health_with_a_single_category_equals_that_score():
    audit = _audit(health_technical=90)
    assert seo_audit_service.overall_health(audit) == 90


def test_overall_health_rounds_to_nearest_int():
    audit = _audit(health_technical=100, health_on_page=99, health_performance=99)
    # (100 + 99 + 99) / 3 = 99.333... -> 99
    assert seo_audit_service.overall_health(audit) == 99


def test_overall_health_uninfluenced_by_categories_not_yet_run():
    """A website that's only had the technical/on-page passes run must not
    be penalized for performance/content/internal-linking scores that
    were never computed -- those stay excluded from the average, not
    treated as zero."""
    with_two = seo_audit_service.overall_health(_audit(health_technical=50, health_on_page=50))
    with_two_low_missing = seo_audit_service.overall_health(
        _audit(health_technical=50, health_on_page=50, health_performance=None)
    )
    assert with_two == with_two_low_missing == 50


# ---------------------------------------------------------------------------
# finding_severity_counts -- integration (needs DB)
# ---------------------------------------------------------------------------

def test_finding_severity_counts_are_real_and_zero_filled(business, db_session):
    website = SeoWebsite(business_id=business["business_id"], url="https://greenleaf.test", crawl_tier="starter")
    db_session.add(website)
    db_session.commit()
    audit = seo_audit_service.create_audit(db_session, website)

    db_session.add(SeoFinding(audit_id=audit.id, business_id=business["business_id"], category="technical", rule_code="a", severity="critical", issue="x"))
    db_session.add(SeoFinding(audit_id=audit.id, business_id=business["business_id"], category="technical", rule_code="b", severity="high", issue="x"))
    db_session.add(SeoFinding(audit_id=audit.id, business_id=business["business_id"], category="technical", rule_code="c", severity="high", issue="x"))
    db_session.commit()

    counts = seo_audit_service.finding_severity_counts(db_session, audit.id)
    assert counts == {"critical": 1, "high": 2, "medium": 0, "low": 0, "informational": 0}


def test_finding_severity_counts_empty_audit_is_all_zero(business, db_session):
    website = SeoWebsite(business_id=business["business_id"], url="https://greenleaf.test", crawl_tier="starter")
    db_session.add(website)
    db_session.commit()
    audit = seo_audit_service.create_audit(db_session, website)

    counts = seo_audit_service.finding_severity_counts(db_session, audit.id)
    assert counts == {"critical": 0, "high": 0, "medium": 0, "low": 0, "informational": 0}


# ---------------------------------------------------------------------------
# HTTP surface -- audit responses carry the summary fields
# ---------------------------------------------------------------------------

def _entitle(business, grant_agent):
    grant_agent(business["business_id"], "seo_audit_optimization")


def _stub_public_url(monkeypatch):
    from app.services import seo_website_service
    monkeypatch.setattr(seo_website_service.web_crawl, "assert_public_url", lambda url: None)


def test_start_audit_response_has_zeroed_summary_fields(client, business, grant_agent, monkeypatch):
    _entitle(business, grant_agent)
    _stub_public_url(monkeypatch)
    create_resp = client.post("/api/agents/seo/websites", json={"url": "https://greenleaf.test"}, headers=business["headers"])
    website_id = create_resp.json()["id"]

    resp = client.post(f"/api/agents/seo/websites/{website_id}/audits", headers=business["headers"])
    body = resp.json()
    assert body["overall_health"] is None
    assert body["finding_counts"] == {"critical": 0, "high": 0, "medium": 0, "low": 0, "informational": 0}


@pytest.fixture()
def use_test_db_for_audit(monkeypatch, db_session):
    monkeypatch.setattr(seo_audit_service, "SessionLocal", lambda: db_session)


@pytest.mark.asyncio
async def test_completed_audit_response_has_real_summary_fields(
    client, business, grant_agent, monkeypatch, db_session, use_test_db_for_audit
):
    _entitle(business, grant_agent)
    _stub_public_url(monkeypatch)
    create_resp = client.post("/api/agents/seo/websites", json={"url": "https://greenleaf.test"}, headers=business["headers"])
    website_id = create_resp.json()["id"]
    audit_resp = client.post(f"/api/agents/seo/websites/{website_id}/audits", headers=business["headers"])
    audit_id = audit_resp.json()["id"]

    monkeypatch.setattr(web_crawl, "discover_website_pages", AsyncMock(return_value=["https://greenleaf.test/gone"]))
    monkeypatch.setattr(
        seo_page_analyzer, "analyze_page",
        AsyncMock(return_value=seo_page_analyzer.PageAnalysis(
            url="https://greenleaf.test/gone", http_status=404, title=None, meta_description=None,
            h1_count=0, word_count=0, canonical_url=None, meta_robots=None, x_robots_tag=None,
            is_indexable=True, redirect_chain=["https://greenleaf.test/gone"], internal_link_count=0,
            image_count=0, images_missing_alt=0, content_hash=None,
        )),
    )
    monkeypatch.setattr(web_crawl, "fetch_robots_txt_text", AsyncMock(return_value=None))
    monkeypatch.setattr(web_crawl, "discover_sitemap_urls", AsyncMock(return_value=[]))

    await seo_audit_service.run_audit(audit_id)

    resp = client.get(f"/api/agents/seo/audits/{audit_id}", headers=business["headers"])
    body = resp.json()
    assert body["status"] == "completed"
    assert body["overall_health"] is not None
    assert body["finding_counts"]["high"] >= 1  # at least the broken_page finding
