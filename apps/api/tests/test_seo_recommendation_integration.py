"""Integration tests for Stage 6 (apps/agents/seo-audit/CLAUDE.md):
run_audit persisting an executive_summary, and the action-plan HTTP
endpoint. Pure rule/LLM-mocking logic is covered by
test_seo_recommendation_service.py; this file covers the wiring.
"""
import json
from unittest.mock import AsyncMock

import pytest

from app.models.seo_audit import SeoAudit
from app.models.seo_website import SeoWebsite
from app.services import seo_audit_service, seo_page_analyzer, seo_recommendation_service, web_crawl
from mielikkix_agent_core import LLMResult


def _entitle(business, grant_agent):
    grant_agent(business["business_id"], "seo_audit_optimization")


def _stub_public_url(monkeypatch):
    from app.services import seo_website_service
    monkeypatch.setattr(seo_website_service.web_crawl, "assert_public_url", lambda url: None)


def _fake_analysis(url: str, **overrides) -> seo_page_analyzer.PageAnalysis:
    defaults = dict(
        url=url, http_status=200, title="Green Leaf Cafe | Organic Coffee in Oslo",
        meta_description="Organic coffee and fresh pastries served daily in downtown Oslo.",
        h1_count=0, word_count=400, canonical_url=url, meta_robots=None, x_robots_tag=None,
        is_indexable=True, redirect_chain=[url], internal_link_count=3, image_count=2, images_missing_alt=0,
        content_hash=f"hash-for-{url}",
    )
    defaults.update(overrides)
    return seo_page_analyzer.PageAnalysis(**defaults)


@pytest.fixture()
def use_test_db_for_audit(monkeypatch, db_session):
    monkeypatch.setattr(seo_audit_service, "SessionLocal", lambda: db_session)


@pytest.mark.asyncio
async def test_run_audit_persists_an_executive_summary(business, db_session, monkeypatch, use_test_db_for_audit):
    website = SeoWebsite(business_id=business["business_id"], url="https://greenleaf.test", crawl_tier="starter")
    db_session.add(website)
    db_session.commit()
    audit = seo_audit_service.create_audit(db_session, website)
    audit_id = audit.id

    monkeypatch.setattr(web_crawl, "discover_website_pages", AsyncMock(return_value=["https://greenleaf.test/"]))
    monkeypatch.setattr(seo_page_analyzer, "analyze_page", AsyncMock(return_value=_fake_analysis("https://greenleaf.test/")))
    monkeypatch.setattr(web_crawl, "fetch_robots_txt_text", AsyncMock(return_value=None))
    monkeypatch.setattr(web_crawl, "discover_sitemap_urls", AsyncMock(return_value=[]))
    monkeypatch.setattr(
        seo_recommendation_service._llm_client, "chat",
        AsyncMock(return_value=LLMResult(text=json.dumps({"summary": "Missing H1 is the top issue to fix."}), usage=None)),
    )

    await seo_audit_service.run_audit(str(audit_id))

    audit = db_session.query(SeoAudit).filter(SeoAudit.id == audit_id).first()
    assert audit.status == "completed"
    assert audit.executive_summary == "Missing H1 is the top issue to fix."


@pytest.mark.asyncio
async def test_run_audit_with_no_findings_has_no_executive_summary(business, db_session, monkeypatch, use_test_db_for_audit):
    """No issues found -> nothing to summarize -> no LLM call, no summary
    (see seo_recommendation_service.generate_executive_summary)."""
    website = SeoWebsite(business_id=business["business_id"], url="https://greenleaf.test", crawl_tier="starter")
    db_session.add(website)
    db_session.commit()
    audit = seo_audit_service.create_audit(db_session, website)
    audit_id = audit.id

    fake_chat = AsyncMock()
    monkeypatch.setattr(web_crawl, "discover_website_pages", AsyncMock(return_value=["https://greenleaf.test/"]))
    monkeypatch.setattr(
        seo_page_analyzer, "analyze_page",
        AsyncMock(return_value=_fake_analysis("https://greenleaf.test/", h1_count=1)),
    )
    monkeypatch.setattr(
        web_crawl, "fetch_robots_txt_text",
        AsyncMock(return_value="User-agent: *\nSitemap: https://greenleaf.test/sitemap.xml\n"),
    )
    monkeypatch.setattr(web_crawl, "discover_sitemap_urls", AsyncMock(return_value=["https://greenleaf.test/"]))
    monkeypatch.setattr(seo_recommendation_service._llm_client, "chat", fake_chat)

    await seo_audit_service.run_audit(str(audit_id))

    audit = db_session.query(SeoAudit).filter(SeoAudit.id == audit_id).first()
    assert audit.executive_summary is None
    fake_chat.assert_not_called()


@pytest.mark.asyncio
async def test_run_audit_completes_even_if_the_llm_call_fails(business, db_session, monkeypatch, use_test_db_for_audit):
    website = SeoWebsite(business_id=business["business_id"], url="https://greenleaf.test", crawl_tier="starter")
    db_session.add(website)
    db_session.commit()
    audit = seo_audit_service.create_audit(db_session, website)
    audit_id = audit.id

    monkeypatch.setattr(web_crawl, "discover_website_pages", AsyncMock(return_value=["https://greenleaf.test/"]))
    monkeypatch.setattr(seo_page_analyzer, "analyze_page", AsyncMock(return_value=_fake_analysis("https://greenleaf.test/")))
    monkeypatch.setattr(web_crawl, "fetch_robots_txt_text", AsyncMock(return_value=None))
    monkeypatch.setattr(web_crawl, "discover_sitemap_urls", AsyncMock(return_value=[]))
    monkeypatch.setattr(seo_recommendation_service._llm_client, "chat", AsyncMock(side_effect=RuntimeError("provider down")))

    await seo_audit_service.run_audit(str(audit_id))

    audit = db_session.query(SeoAudit).filter(SeoAudit.id == audit_id).first()
    assert audit.status == "completed"  # one failed LLM call must not fail the whole audit
    assert audit.executive_summary is None


# ---------------------------------------------------------------------------
# HTTP surface
# ---------------------------------------------------------------------------

def test_action_plan_requires_entitlement(client, business):
    resp = client.get(
        "/api/agents/seo/audits/00000000-0000-0000-0000-000000000000/action-plan", headers=business["headers"]
    )
    assert resp.status_code == 403


def test_action_plan_404s_for_unknown_audit(client, business, grant_agent):
    _entitle(business, grant_agent)
    resp = client.get(
        "/api/agents/seo/audits/00000000-0000-0000-0000-000000000000/action-plan", headers=business["headers"]
    )
    assert resp.status_code == 404


def test_action_plan_groups_and_prioritizes_real_findings(client, business, grant_agent, monkeypatch, db_session):
    from app.models.seo_audit import SeoFinding

    _entitle(business, grant_agent)
    _stub_public_url(monkeypatch)
    create_resp = client.post("/api/agents/seo/websites", json={"url": "https://greenleaf.test"}, headers=business["headers"])
    website_id = create_resp.json()["id"]
    audit_resp = client.post(f"/api/agents/seo/websites/{website_id}/audits", headers=business["headers"])
    audit_id = audit_resp.json()["id"]

    db_session.add(SeoFinding(
        audit_id=audit_id, business_id=business["business_id"], category="technical",
        rule_code="robots_blocks_entire_site", severity="critical", issue="robots.txt blocks everything",
        affected_url="https://greenleaf.test",
    ))
    db_session.add(SeoFinding(
        audit_id=audit_id, business_id=business["business_id"], category="on_page",
        rule_code="missing_h1", severity="high", issue="No H1", affected_url="https://greenleaf.test/a",
    ))
    db_session.commit()

    resp = client.get(f"/api/agents/seo/audits/{audit_id}/action-plan", headers=business["headers"])

    assert resp.status_code == 200
    body = resp.json()
    assert len(body) == 2
    assert body[0]["priority"] == 1
    assert body[0]["rule_code"] == "robots_blocks_entire_site"


def test_cannot_get_another_businesss_action_plan(client, business, signup, grant_agent, monkeypatch):
    _entitle(business, grant_agent)
    other = signup()
    grant_agent(other["business_id"], "seo_audit_optimization")
    _stub_public_url(monkeypatch)

    create_resp = client.post("/api/agents/seo/websites", json={"url": "https://theirs.test"}, headers=other["headers"])
    website_id = create_resp.json()["id"]
    audit_resp = client.post(f"/api/agents/seo/websites/{website_id}/audits", headers=other["headers"])
    audit_id = audit_resp.json()["id"]

    resp = client.get(f"/api/agents/seo/audits/{audit_id}/action-plan", headers=business["headers"])
    assert resp.status_code == 404
