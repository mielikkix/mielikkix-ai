"""Integration tests for Stage 14 (apps/agents/seo-audit/CLAUDE.md's
"Professional tier roadmap"): run_audit's accessibility-analyzer pass
actually producing SeoFinding rows folded into health_on_page. Pure rule
logic is covered by test_seo_accessibility_analyzer.py; this file covers
the wiring alongside the Stage 4 on-page pass that runs in the same audit.
"""
from unittest.mock import AsyncMock

import pytest

from app.models.seo_audit import SeoAudit, SeoFinding
from app.models.seo_website import SeoWebsite
from app.services import seo_audit_service, seo_page_analyzer, web_crawl


def _fake_analysis(url: str, **overrides) -> seo_page_analyzer.PageAnalysis:
    defaults = dict(
        url=url, http_status=200,
        title="Green Leaf Cafe | Organic Coffee in Oslo",
        meta_description="Organic coffee and fresh pastries served daily in downtown Oslo.",
        h1_count=1, word_count=400, canonical_url=url, meta_robots=None, x_robots_tag=None,
        is_indexable=True, redirect_chain=[url], internal_link_count=3, image_count=2, images_missing_alt=0,
        structured_data_types=["Organization"],
    )
    defaults.update(overrides)
    return seo_page_analyzer.PageAnalysis(**defaults)


@pytest.fixture()
def use_test_db_for_audit(monkeypatch, db_session):
    monkeypatch.setattr(seo_audit_service, "SessionLocal", lambda: db_session)


async def _run(business, db_session, monkeypatch, analysis):
    website = SeoWebsite(business_id=business["business_id"], url="https://greenleaf.test", crawl_tier="starter")
    db_session.add(website)
    db_session.commit()
    audit = seo_audit_service.create_audit(db_session, website)
    audit_id = audit.id  # captured before run_audit closes this session -- see its own finally: db.close()

    monkeypatch.setattr(web_crawl, "discover_website_pages", AsyncMock(return_value=[analysis.url]))
    monkeypatch.setattr(seo_page_analyzer, "analyze_page", AsyncMock(return_value=analysis))
    monkeypatch.setattr(
        web_crawl, "fetch_robots_txt_text",
        AsyncMock(return_value="User-agent: *\nSitemap: https://greenleaf.test/sitemap.xml\n"),
    )
    monkeypatch.setattr(web_crawl, "discover_sitemap_urls", AsyncMock(return_value=["https://greenleaf.test/sitemap.xml"]))

    await seo_audit_service.run_audit(str(audit_id))
    return db_session.query(SeoAudit).filter(SeoAudit.id == audit_id).first()


@pytest.mark.asyncio
async def test_run_audit_flags_missing_html_lang(business, db_session, monkeypatch, use_test_db_for_audit):
    analysis = _fake_analysis("https://greenleaf.test/", html_lang_present=False, heading_outline=[1])
    audit = await _run(business, db_session, monkeypatch, analysis)

    assert audit.status == "completed"
    findings = db_session.query(SeoFinding).filter(SeoFinding.audit_id == audit.id).all()
    codes = {f.rule_code for f in findings}
    assert "missing_html_lang" in codes
    assert all(f.category == "on_page" for f in findings if f.rule_code == "missing_html_lang")
    assert audit.health_on_page < 100


@pytest.mark.asyncio
async def test_run_audit_flags_form_inputs_missing_label(business, db_session, monkeypatch, use_test_db_for_audit):
    analysis = _fake_analysis("https://greenleaf.test/", html_lang_present=True, heading_outline=[1], form_inputs_missing_label=2)
    audit = await _run(business, db_session, monkeypatch, analysis)

    findings = db_session.query(SeoFinding).filter(SeoFinding.audit_id == audit.id, SeoFinding.rule_code == "form_inputs_missing_label").all()
    assert len(findings) == 1
    assert findings[0].evidence == {"form_inputs_missing_label": 2}


@pytest.mark.asyncio
async def test_run_audit_with_no_accessibility_issues_has_no_accessibility_findings(business, db_session, monkeypatch, use_test_db_for_audit):
    analysis = _fake_analysis("https://greenleaf.test/", html_lang_present=True, heading_outline=[1, 2])
    audit = await _run(business, db_session, monkeypatch, analysis)

    findings = db_session.query(SeoFinding).filter(SeoFinding.audit_id == audit.id).all()
    codes = {f.rule_code for f in findings}
    assert "missing_html_lang" not in codes
    assert "heading_hierarchy_skip" not in codes
    assert "form_inputs_missing_label" not in codes
    assert "links_missing_accessible_name" not in codes
    assert audit.health_on_page == 100
