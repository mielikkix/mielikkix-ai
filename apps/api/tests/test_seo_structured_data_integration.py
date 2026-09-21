"""Integration tests for Stage 13 (apps/agents/seo-audit/CLAUDE.md's
"Professional tier roadmap"): run_audit's structured-data-analyzer pass
actually producing SeoFinding rows folded into health_technical. Pure rule
logic is covered by test_seo_structured_data_analyzer.py; this file covers
the wiring alongside the Stage 3 technical pass that runs in the same audit.
"""
from unittest.mock import AsyncMock

import pytest

from app.models.seo_audit import SeoAudit, SeoFinding
from app.models.seo_website import SeoWebsite
from app.services import seo_audit_service, seo_page_analyzer, web_crawl


def _fake_analysis(url: str, **overrides) -> seo_page_analyzer.PageAnalysis:
    defaults = dict(
        url=url, http_status=200, title="A title", meta_description="A description",
        h1_count=1, word_count=400, canonical_url=url, meta_robots=None, x_robots_tag=None,
        is_indexable=True, redirect_chain=[url], internal_link_count=3, image_count=2, images_missing_alt=0,
    )
    defaults.update(overrides)
    return seo_page_analyzer.PageAnalysis(**defaults)


@pytest.fixture()
def use_test_db_for_audit(monkeypatch, db_session):
    monkeypatch.setattr(seo_audit_service, "SessionLocal", lambda: db_session)


async def _run(business, db_session, monkeypatch, analysis, robots_txt="User-agent: *\nSitemap: https://greenleaf.test/sitemap.xml\n"):
    website = SeoWebsite(business_id=business["business_id"], url="https://greenleaf.test", crawl_tier="starter")
    db_session.add(website)
    db_session.commit()
    audit = seo_audit_service.create_audit(db_session, website)
    audit_id = audit.id  # captured before run_audit closes this session -- see its own finally: db.close()

    monkeypatch.setattr(web_crawl, "discover_website_pages", AsyncMock(return_value=[analysis.url]))
    monkeypatch.setattr(seo_page_analyzer, "analyze_page", AsyncMock(return_value=analysis))
    monkeypatch.setattr(web_crawl, "fetch_robots_txt_text", AsyncMock(return_value=robots_txt))
    monkeypatch.setattr(web_crawl, "discover_sitemap_urls", AsyncMock(return_value=["https://greenleaf.test/sitemap.xml"]))

    await seo_audit_service.run_audit(str(audit_id))
    return db_session.query(SeoAudit).filter(SeoAudit.id == audit_id).first()


@pytest.mark.asyncio
async def test_run_audit_flags_invalid_json_ld(business, db_session, monkeypatch, use_test_db_for_audit):
    analysis = _fake_analysis("https://greenleaf.test/", structured_data_invalid_count=1, structured_data_types=[])
    audit = await _run(business, db_session, monkeypatch, analysis)

    assert audit.status == "completed"
    findings = db_session.query(SeoFinding).filter(SeoFinding.audit_id == audit.id).all()
    codes = {f.rule_code for f in findings}
    assert "structured_data_invalid_json" in codes
    assert all(f.category == "technical" for f in findings if f.rule_code == "structured_data_invalid_json")


@pytest.mark.asyncio
async def test_run_audit_flags_sitewide_absence_of_structured_data(business, db_session, monkeypatch, use_test_db_for_audit):
    analysis = _fake_analysis("https://greenleaf.test/", structured_data_types=[])
    audit = await _run(business, db_session, monkeypatch, analysis)

    findings = db_session.query(SeoFinding).filter(SeoFinding.audit_id == audit.id, SeoFinding.rule_code == "no_structured_data_sitewide").all()
    assert len(findings) == 1
    assert audit.health_technical < 100


@pytest.mark.asyncio
async def test_run_audit_with_structured_data_present_has_no_absence_finding(business, db_session, monkeypatch, use_test_db_for_audit):
    analysis = _fake_analysis("https://greenleaf.test/", structured_data_types=["Organization"])
    audit = await _run(business, db_session, monkeypatch, analysis)

    findings = db_session.query(SeoFinding).filter(SeoFinding.audit_id == audit.id).all()
    codes = {f.rule_code for f in findings}
    assert "no_structured_data_sitewide" not in codes
    assert "structured_data_invalid_json" not in codes
