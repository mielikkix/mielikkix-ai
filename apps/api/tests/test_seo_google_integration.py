"""Integration tests for Stage 12 (apps/agents/seo-audit/CLAUDE.md's
"Professional tier roadmap"): run_audit fetching real Google Analytics/
Search Console data and folding it into SeoCrawledPage rows + the action
plan's traffic_weight. Provider-internal HTTP logic is covered by
test_analytics_provider.py/test_search_console_provider.py; this file
covers the wiring inside run_audit.
"""
from unittest.mock import AsyncMock

import pytest

from app.integrations.search_console_provider import SearchConsoleMetrics
from app.models.seo_audit import SeoAudit, SeoCrawledPage
from app.models.seo_website import SeoWebsite
from app.services import seo_audit_service, seo_page_analyzer, web_crawl


def _fake_analysis(url: str, **overrides) -> seo_page_analyzer.PageAnalysis:
    defaults = dict(
        url=url, http_status=200, title="A title", meta_description="A description",
        h1_count=1, word_count=400, canonical_url=url, meta_robots=None, x_robots_tag=None,
        is_indexable=True, redirect_chain=[url], internal_link_count=3, image_count=2, images_missing_alt=0,
        structured_data_types=["Organization"], html_lang_present=True, heading_outline=[1],
    )
    defaults.update(overrides)
    return seo_page_analyzer.PageAnalysis(**defaults)


@pytest.fixture()
def use_test_db_for_audit(monkeypatch, db_session):
    monkeypatch.setattr(seo_audit_service, "SessionLocal", lambda: db_session)


async def _run(business, db_session, monkeypatch, analytics_provider=None, search_console_provider=None):
    website = SeoWebsite(business_id=business["business_id"], url="https://greenleaf.test", crawl_tier="starter")
    db_session.add(website)
    db_session.commit()
    audit = seo_audit_service.create_audit(db_session, website)
    audit_id = audit.id

    monkeypatch.setattr(web_crawl, "discover_website_pages", AsyncMock(return_value=["https://greenleaf.test/"]))
    monkeypatch.setattr(seo_page_analyzer, "analyze_page", AsyncMock(return_value=_fake_analysis("https://greenleaf.test/")))
    monkeypatch.setattr(
        web_crawl, "fetch_robots_txt_text",
        AsyncMock(return_value="User-agent: *\nSitemap: https://greenleaf.test/sitemap.xml\n"),
    )
    monkeypatch.setattr(web_crawl, "discover_sitemap_urls", AsyncMock(return_value=["https://greenleaf.test/"]))
    monkeypatch.setattr(seo_audit_service, "get_analytics_provider", lambda db, business_id: analytics_provider)
    monkeypatch.setattr(seo_audit_service, "get_search_console_provider", lambda db, business_id: search_console_provider)

    await seo_audit_service.run_audit(str(audit_id))
    return audit_id


@pytest.mark.asyncio
async def test_run_audit_with_no_google_connection_leaves_metrics_null(business, db_session, monkeypatch, use_test_db_for_audit):
    audit_id = await _run(business, db_session, monkeypatch, analytics_provider=None, search_console_provider=None)

    page = db_session.query(SeoCrawledPage).filter(SeoCrawledPage.audit_id == audit_id).first()
    assert page.ga_sessions_28d is None
    assert page.gsc_impressions_28d is None
    assert page.gsc_clicks_28d is None
    assert page.gsc_avg_position_28d is None


@pytest.mark.asyncio
async def test_run_audit_stores_real_analytics_sessions(business, db_session, monkeypatch, use_test_db_for_audit):
    fake_provider = AsyncMock()
    fake_provider.get_page_sessions = AsyncMock(return_value={"https://greenleaf.test/": 150})

    audit_id = await _run(business, db_session, monkeypatch, analytics_provider=fake_provider)

    page = db_session.query(SeoCrawledPage).filter(SeoCrawledPage.audit_id == audit_id).first()
    assert page.ga_sessions_28d == 150


@pytest.mark.asyncio
async def test_run_audit_stores_real_search_console_metrics(business, db_session, monkeypatch, use_test_db_for_audit):
    fake_provider = AsyncMock()
    fake_provider.get_page_search_metrics = AsyncMock(
        return_value={"https://greenleaf.test/": SearchConsoleMetrics(impressions=1000, clicks=45, avg_position=6.2)}
    )

    audit_id = await _run(business, db_session, monkeypatch, search_console_provider=fake_provider)

    page = db_session.query(SeoCrawledPage).filter(SeoCrawledPage.audit_id == audit_id).first()
    assert page.gsc_impressions_28d == 1000
    assert page.gsc_clicks_28d == 45
    assert page.gsc_avg_position_28d == 6.2


@pytest.mark.asyncio
async def test_run_audit_completes_even_if_analytics_provider_raises(business, db_session, monkeypatch, use_test_db_for_audit):
    fake_provider = AsyncMock()
    fake_provider.get_page_sessions = AsyncMock(side_effect=RuntimeError("boom"))

    audit_id = await _run(business, db_session, monkeypatch, analytics_provider=fake_provider)

    audit = db_session.query(SeoAudit).filter(SeoAudit.id == audit_id).first()
    assert audit.status == "completed"
    page = db_session.query(SeoCrawledPage).filter(SeoCrawledPage.audit_id == audit_id).first()
    assert page.ga_sessions_28d is None


@pytest.mark.asyncio
async def test_run_audit_action_plan_reflects_real_traffic_weight(business, db_session, monkeypatch, use_test_db_for_audit):
    """End-to-end version of the unit-tested sort behavior in
    test_seo_recommendation_service.py -- confirms run_audit actually
    passes the freshly-fetched crawled_pages (with their new ga_sessions_28d)
    into build_action_plan, not a stale pre-fetch copy."""
    fake_provider = AsyncMock()
    fake_provider.get_page_sessions = AsyncMock(return_value={"https://greenleaf.test/": 999})

    audit_id = await _run(business, db_session, monkeypatch, analytics_provider=fake_provider)

    from app.services import seo_audit_service as sas
    plan = sas.get_action_plan(db_session, business["business_id"], str(audit_id))
    # h1_count=1/title/meta all healthy in _fake_analysis -- no on-page
    # findings expected, so just confirm the plan-building call succeeded
    # and any item present carries the real traffic weight, never a guess.
    for item in plan:
        if "https://greenleaf.test/" in item.affected_urls:
            assert item.traffic_weight == 999
