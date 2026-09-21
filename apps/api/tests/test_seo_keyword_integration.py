"""Integration tests for Stage 9 (apps/agents/seo-audit/CLAUDE.md):
run_audit's keyword pass actually producing SeoKeywordOpportunity rows, and
the keyword-opportunities HTTP endpoint. Pure service logic is covered by
test_seo_keyword_service.py; this file covers the wiring.
"""
import json
from unittest.mock import AsyncMock

import pytest

from app.models.seo_audit import SeoAudit, SeoKeywordOpportunity
from app.models.seo_website import SeoWebsite
from app.services import seo_audit_service, seo_keyword_service, seo_page_analyzer, seo_recommendation_service, web_crawl
from mielikkix_agent_core import LLMResult


def _fake_analysis(url: str, **overrides) -> seo_page_analyzer.PageAnalysis:
    defaults = dict(
        url=url, http_status=200, title="Green Leaf Cafe | Organic Coffee in Oslo",
        meta_description="Organic coffee and fresh pastries served daily in downtown Oslo.",
        h1_count=1, word_count=400, canonical_url=url, meta_robots=None, x_robots_tag=None,
        is_indexable=True, redirect_chain=[url], internal_link_count=3, image_count=2, images_missing_alt=0,
        content_hash=f"hash-for-{url}",
    )
    defaults.update(overrides)
    return seo_page_analyzer.PageAnalysis(**defaults)


@pytest.fixture()
def use_test_db_for_audit(monkeypatch, db_session):
    monkeypatch.setattr(seo_audit_service, "SessionLocal", lambda: db_session)


def _stub_crawl_and_recommendation_llm(monkeypatch):
    monkeypatch.setattr(web_crawl, "discover_website_pages", AsyncMock(return_value=["https://greenleaf.test/"]))
    monkeypatch.setattr(seo_page_analyzer, "analyze_page", AsyncMock(return_value=_fake_analysis("https://greenleaf.test/")))
    monkeypatch.setattr(web_crawl, "fetch_robots_txt_text", AsyncMock(return_value=None))
    monkeypatch.setattr(web_crawl, "discover_sitemap_urls", AsyncMock(return_value=[]))
    monkeypatch.setattr(seo_recommendation_service._llm_client, "chat", AsyncMock(side_effect=RuntimeError("not used")))
    monkeypatch.setattr("app.core.config.settings.google_pagespeed_api_key", "")


@pytest.mark.asyncio
async def test_run_audit_persists_keyword_opportunities(business, db_session, monkeypatch, use_test_db_for_audit):
    website = SeoWebsite(business_id=business["business_id"], url="https://greenleaf.test", crawl_tier="starter")
    db_session.add(website)
    db_session.commit()
    audit = seo_audit_service.create_audit(db_session, website)
    audit_id = audit.id

    _stub_crawl_and_recommendation_llm(monkeypatch)
    response = json.dumps({"keywords": [
        {"keyword": "organic coffee oslo", "intent": "commercial", "suggested_page": "https://greenleaf.test/",
         "current_page": "https://greenleaf.test/", "content_gap": None, "recommendation": "Mention 'organic' more."},
    ]})
    monkeypatch.setattr(seo_keyword_service._llm_client, "chat", AsyncMock(return_value=LLMResult(text=response, usage=None)))

    await seo_audit_service.run_audit(str(audit_id))

    audit = db_session.query(SeoAudit).filter(SeoAudit.id == audit_id).first()
    assert audit.status == "completed"

    opportunities = db_session.query(SeoKeywordOpportunity).filter(SeoKeywordOpportunity.audit_id == audit_id).all()
    assert len(opportunities) == 1
    assert opportunities[0].keyword == "organic coffee oslo"
    assert opportunities[0].volume == "Not available"


@pytest.mark.asyncio
async def test_run_audit_completes_even_if_keyword_generation_fails(business, db_session, monkeypatch, use_test_db_for_audit):
    website = SeoWebsite(business_id=business["business_id"], url="https://greenleaf.test", crawl_tier="starter")
    db_session.add(website)
    db_session.commit()
    audit = seo_audit_service.create_audit(db_session, website)
    audit_id = audit.id

    _stub_crawl_and_recommendation_llm(monkeypatch)
    monkeypatch.setattr(seo_keyword_service._llm_client, "chat", AsyncMock(side_effect=RuntimeError("provider down")))

    await seo_audit_service.run_audit(str(audit_id))

    audit = db_session.query(SeoAudit).filter(SeoAudit.id == audit_id).first()
    assert audit.status == "completed"  # a failed keyword pass must not fail the whole audit

    opportunities = db_session.query(SeoKeywordOpportunity).filter(SeoKeywordOpportunity.audit_id == audit_id).all()
    assert opportunities == []


def test_list_keyword_opportunities_endpoint(client, business, grant_agent, db_session, monkeypatch):
    from app.services import seo_website_service
    monkeypatch.setattr(seo_website_service.web_crawl, "assert_public_url", lambda url: None)
    grant_agent(business["business_id"], "seo_audit_optimization")

    create_resp = client.post("/api/agents/seo/websites", json={"url": "https://greenleaf.test"}, headers=business["headers"])
    website_id = create_resp.json()["id"]
    audit_resp = client.post(f"/api/agents/seo/websites/{website_id}/audits", headers=business["headers"])
    audit_id = audit_resp.json()["id"]

    db_session.add(SeoKeywordOpportunity(
        audit_id=audit_id, business_id=business["business_id"], keyword="organic coffee oslo",
        intent="commercial", volume="Not available",
    ))
    db_session.commit()

    resp = client.get(f"/api/agents/seo/audits/{audit_id}/keyword-opportunities", headers=business["headers"])

    assert resp.status_code == 200
    body = resp.json()
    assert len(body) == 1
    assert body[0]["keyword"] == "organic coffee oslo"
    assert body[0]["volume"] == "Not available"


def test_list_keyword_opportunities_requires_entitlement(client, business):
    resp = client.get(
        "/api/agents/seo/audits/00000000-0000-0000-0000-000000000000/keyword-opportunities",
        headers=business["headers"],
    )
    assert resp.status_code == 403


def test_list_keyword_opportunities_404s_for_unknown_audit(client, business, grant_agent):
    grant_agent(business["business_id"], "seo_audit_optimization")
    resp = client.get(
        "/api/agents/seo/audits/00000000-0000-0000-0000-000000000000/keyword-opportunities",
        headers=business["headers"],
    )
    assert resp.status_code == 404


def test_cannot_list_another_businesss_keyword_opportunities(client, business, signup, grant_agent, monkeypatch):
    from app.services import seo_website_service
    monkeypatch.setattr(seo_website_service.web_crawl, "assert_public_url", lambda url: None)
    grant_agent(business["business_id"], "seo_audit_optimization")
    other = signup()
    grant_agent(other["business_id"], "seo_audit_optimization")

    create_resp = client.post("/api/agents/seo/websites", json={"url": "https://theirs.test"}, headers=other["headers"])
    website_id = create_resp.json()["id"]
    audit_resp = client.post(f"/api/agents/seo/websites/{website_id}/audits", headers=other["headers"])
    audit_id = audit_resp.json()["id"]

    resp = client.get(f"/api/agents/seo/audits/{audit_id}/keyword-opportunities", headers=business["headers"])
    assert resp.status_code == 404
