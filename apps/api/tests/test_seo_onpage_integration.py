"""Integration tests for Stage 4 (apps/agents/seo-audit/CLAUDE.md):
run_audit's on-page-analyzer pass actually producing SeoFinding rows and a
health_on_page score. Pure rule logic is covered by
test_seo_onpage_analyzer.py; this file covers the wiring alongside the
Stage 3 technical pass that runs in the same audit.
"""
from unittest.mock import AsyncMock

import pytest

from app.models.seo_audit import SeoAudit, SeoFinding
from app.models.seo_website import SeoWebsite
from app.services import seo_audit_service, seo_page_analyzer, web_crawl


def _fake_analysis(url: str, **overrides) -> seo_page_analyzer.PageAnalysis:
    defaults = dict(
        url=url, http_status=200,
        title="Green Leaf Cafe | Organic Coffee in Oslo",  # within TITLE_MIN/MAX_LENGTH
        meta_description="Organic coffee and fresh pastries served daily in downtown Oslo.",  # within META_DESCRIPTION_MIN/MAX_LENGTH
        h1_count=1, word_count=400, canonical_url=url, meta_robots=None, x_robots_tag=None,
        is_indexable=True, redirect_chain=[url], internal_link_count=3, image_count=2, images_missing_alt=0,
        content_hash=f"hash-for-{url}",
    )
    defaults.update(overrides)
    return seo_page_analyzer.PageAnalysis(**defaults)


@pytest.fixture()
def use_test_db_for_audit(monkeypatch, db_session):
    monkeypatch.setattr(seo_audit_service, "SessionLocal", lambda: db_session)


@pytest.mark.asyncio
async def test_run_audit_produces_onpage_findings_and_health_score(business, db_session, monkeypatch, use_test_db_for_audit):
    website = SeoWebsite(business_id=business["business_id"], url="https://greenleaf.test", crawl_tier="starter")
    db_session.add(website)
    db_session.commit()
    audit = seo_audit_service.create_audit(db_session, website)
    audit_id = audit.id

    monkeypatch.setattr(web_crawl, "discover_website_pages", AsyncMock(return_value=["https://greenleaf.test/thin"]))
    monkeypatch.setattr(
        seo_page_analyzer, "analyze_page",
        AsyncMock(return_value=_fake_analysis("https://greenleaf.test/thin", word_count=20, h1_count=0)),
    )
    monkeypatch.setattr(web_crawl, "fetch_robots_txt_text", AsyncMock(return_value=None))
    monkeypatch.setattr(web_crawl, "discover_sitemap_urls", AsyncMock(return_value=[]))

    await seo_audit_service.run_audit(str(audit_id))

    audit = db_session.query(SeoAudit).filter(SeoAudit.id == audit_id).first()
    assert audit.status == "completed"
    assert audit.health_on_page is not None
    assert audit.health_on_page < 100  # missing H1 + thin content both deduct

    findings = db_session.query(SeoFinding).filter(SeoFinding.audit_id == audit_id, SeoFinding.category == "on_page").all()
    codes = {f.rule_code for f in findings}
    assert "missing_h1" in codes
    assert "thin_content" in codes


@pytest.mark.asyncio
async def test_run_audit_flags_duplicate_titles_across_crawled_pages(business, db_session, monkeypatch, use_test_db_for_audit):
    website = SeoWebsite(business_id=business["business_id"], url="https://greenleaf.test", crawl_tier="starter")
    db_session.add(website)
    db_session.commit()
    audit = seo_audit_service.create_audit(db_session, website)
    audit_id = audit.id

    urls = ["https://greenleaf.test/a", "https://greenleaf.test/b"]
    monkeypatch.setattr(web_crawl, "discover_website_pages", AsyncMock(return_value=urls))
    monkeypatch.setattr(
        seo_page_analyzer, "analyze_page",
        AsyncMock(side_effect=lambda u: _fake_analysis(u, title="Duplicate Title Everywhere")),
    )
    monkeypatch.setattr(web_crawl, "fetch_robots_txt_text", AsyncMock(return_value=None))
    monkeypatch.setattr(web_crawl, "discover_sitemap_urls", AsyncMock(return_value=[]))

    await seo_audit_service.run_audit(str(audit_id))

    findings = db_session.query(SeoFinding).filter(SeoFinding.audit_id == audit_id, SeoFinding.rule_code == "duplicate_title").all()
    assert {f.affected_url for f in findings} == set(urls)


@pytest.mark.asyncio
async def test_run_audit_with_no_onpage_issues_has_a_perfect_onpage_score(business, db_session, monkeypatch, use_test_db_for_audit):
    website = SeoWebsite(business_id=business["business_id"], url="https://greenleaf.test", crawl_tier="starter")
    db_session.add(website)
    db_session.commit()
    audit = seo_audit_service.create_audit(db_session, website)
    audit_id = audit.id

    monkeypatch.setattr(web_crawl, "discover_website_pages", AsyncMock(return_value=["https://greenleaf.test/"]))
    monkeypatch.setattr(
        seo_page_analyzer, "analyze_page",
        # structured_data_types/html_lang_present/heading_outline set so
        # Stage 13/14's checks don't fire -- this test's whole point is a
        # truly perfect score, which now includes those checks too.
        AsyncMock(return_value=_fake_analysis(
            "https://greenleaf.test/",
            structured_data_types=["Organization"],
            html_lang_present=True,
            heading_outline=[1],
        )),
    )
    monkeypatch.setattr(
        web_crawl, "fetch_robots_txt_text",
        AsyncMock(return_value="User-agent: *\nSitemap: https://greenleaf.test/sitemap.xml\n"),
    )
    monkeypatch.setattr(web_crawl, "discover_sitemap_urls", AsyncMock(return_value=["https://greenleaf.test/"]))

    await seo_audit_service.run_audit(str(audit_id))

    audit = db_session.query(SeoAudit).filter(SeoAudit.id == audit_id).first()
    assert audit.health_on_page == 100
    assert audit.health_technical == 100
