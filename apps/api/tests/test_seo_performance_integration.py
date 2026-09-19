"""Integration tests for Stage 8 (apps/agents/seo-copywriter/CLAUDE.md):
run_audit's performance pass actually calling the PerformanceProvider,
persisting SeoPerformanceMeasurement rows, and computing health_performance
-- or honestly leaving it null when no measurement is available. Pure
provider logic is covered by test_performance_provider.py; this file
covers the wiring.
"""
from unittest.mock import AsyncMock

import pytest

from app.integrations.performance_provider import PerformanceMetrics
from app.models.seo_audit import SeoAudit, SeoPerformanceMeasurement
from app.models.seo_website import SeoWebsite
from app.services import seo_audit_service, seo_page_analyzer, web_crawl


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


def _stub_crawl_and_llm(monkeypatch):
    monkeypatch.setattr(web_crawl, "discover_website_pages", AsyncMock(return_value=["https://greenleaf.test/"]))
    monkeypatch.setattr(seo_page_analyzer, "analyze_page", AsyncMock(return_value=_fake_analysis("https://greenleaf.test/")))
    monkeypatch.setattr(web_crawl, "fetch_robots_txt_text", AsyncMock(return_value=None))
    monkeypatch.setattr(web_crawl, "discover_sitemap_urls", AsyncMock(return_value=[]))
    from app.services import seo_recommendation_service
    monkeypatch.setattr(seo_recommendation_service._llm_client, "chat", AsyncMock(side_effect=RuntimeError("not used")))


@pytest.mark.asyncio
async def test_run_audit_with_no_provider_leaves_health_performance_null(business, db_session, monkeypatch, use_test_db_for_audit):
    """No API key configured -- the default state of this repo -- must
    leave health_performance null, never a guessed number."""
    website = SeoWebsite(business_id=business["business_id"], url="https://greenleaf.test", crawl_tier="starter")
    db_session.add(website)
    db_session.commit()
    audit = seo_audit_service.create_audit(db_session, website)
    audit_id = audit.id

    _stub_crawl_and_llm(monkeypatch)
    monkeypatch.setattr("app.core.config.settings.google_pagespeed_api_key", "")

    await seo_audit_service.run_audit(str(audit_id))

    audit = db_session.query(SeoAudit).filter(SeoAudit.id == audit_id).first()
    assert audit.status == "completed"
    assert audit.health_performance is None
    measurements = db_session.query(SeoPerformanceMeasurement).filter(SeoPerformanceMeasurement.audit_id == audit_id).all()
    assert measurements == []


@pytest.mark.asyncio
async def test_run_audit_stores_a_measurement_per_successful_strategy(business, db_session, monkeypatch, use_test_db_for_audit):
    website = SeoWebsite(business_id=business["business_id"], url="https://greenleaf.test", crawl_tier="starter")
    db_session.add(website)
    db_session.commit()
    audit = seo_audit_service.create_audit(db_session, website)
    audit_id = audit.id

    _stub_crawl_and_llm(monkeypatch)

    async def fake_measure(url, strategy):
        return PerformanceMetrics(strategy=strategy, performance_score=90 if strategy == "mobile" else 70, lcp_ms=2000, cls=0.02, inp_ms=None, tbt_ms=100)

    fake_provider = AsyncMock()
    fake_provider.measure = fake_measure
    monkeypatch.setattr(seo_audit_service, "get_performance_provider", lambda: fake_provider)

    await seo_audit_service.run_audit(str(audit_id))

    audit = db_session.query(SeoAudit).filter(SeoAudit.id == audit_id).first()
    assert audit.status == "completed"
    assert audit.health_performance == 80  # average of 90 (mobile) and 70 (desktop)

    measurements = db_session.query(SeoPerformanceMeasurement).filter(SeoPerformanceMeasurement.audit_id == audit_id).all()
    assert {m.strategy for m in measurements} == {"mobile", "desktop"}


@pytest.mark.asyncio
async def test_run_audit_handles_one_strategy_succeeding_and_one_failing(business, db_session, monkeypatch, use_test_db_for_audit):
    website = SeoWebsite(business_id=business["business_id"], url="https://greenleaf.test", crawl_tier="starter")
    db_session.add(website)
    db_session.commit()
    audit = seo_audit_service.create_audit(db_session, website)
    audit_id = audit.id

    _stub_crawl_and_llm(monkeypatch)

    async def fake_measure(url, strategy):
        if strategy == "desktop":
            return None
        return PerformanceMetrics(strategy="mobile", performance_score=85, lcp_ms=1800, cls=0.01, inp_ms=None, tbt_ms=90)

    fake_provider = AsyncMock()
    fake_provider.measure = fake_measure
    monkeypatch.setattr(seo_audit_service, "get_performance_provider", lambda: fake_provider)

    await seo_audit_service.run_audit(str(audit_id))

    audit = db_session.query(SeoAudit).filter(SeoAudit.id == audit_id).first()
    assert audit.health_performance == 85

    measurements = db_session.query(SeoPerformanceMeasurement).filter(SeoPerformanceMeasurement.audit_id == audit_id).all()
    assert len(measurements) == 1
    assert measurements[0].strategy == "mobile"


@pytest.mark.asyncio
async def test_run_audit_completes_even_if_performance_provider_raises(business, db_session, monkeypatch, use_test_db_for_audit):
    website = SeoWebsite(business_id=business["business_id"], url="https://greenleaf.test", crawl_tier="starter")
    db_session.add(website)
    db_session.commit()
    audit = seo_audit_service.create_audit(db_session, website)
    audit_id = audit.id

    _stub_crawl_and_llm(monkeypatch)

    fake_provider = AsyncMock()
    fake_provider.measure = AsyncMock(side_effect=RuntimeError("provider exploded"))
    monkeypatch.setattr(seo_audit_service, "get_performance_provider", lambda: fake_provider)

    await seo_audit_service.run_audit(str(audit_id))

    audit = db_session.query(SeoAudit).filter(SeoAudit.id == audit_id).first()
    assert audit.status == "completed"
    assert audit.health_performance is None


def test_list_audit_performance_endpoint(client, business, grant_agent, db_session, monkeypatch):
    from app.services import seo_website_service
    monkeypatch.setattr(seo_website_service.web_crawl, "assert_public_url", lambda url: None)
    grant_agent(business["business_id"], "seo_audit_optimization")

    create_resp = client.post("/api/agents/seo/websites", json={"url": "https://greenleaf.test"}, headers=business["headers"])
    website_id = create_resp.json()["id"]
    audit_resp = client.post(f"/api/agents/seo/websites/{website_id}/audits", headers=business["headers"])
    audit_id = audit_resp.json()["id"]

    db_session.add(SeoPerformanceMeasurement(
        audit_id=audit_id, strategy="mobile", performance_score=88, lcp_ms=2100, cls=0.03, inp_ms=200, tbt_ms=120,
    ))
    db_session.commit()

    resp = client.get(f"/api/agents/seo/audits/{audit_id}/performance", headers=business["headers"])

    assert resp.status_code == 200
    body = resp.json()
    assert len(body) == 1
    assert body[0]["strategy"] == "mobile"
    assert body[0]["performance_score"] == 88
    assert body[0]["cls_score"] == 0.03


def test_list_audit_performance_empty_when_not_measured(client, business, grant_agent, monkeypatch):
    from app.services import seo_website_service
    monkeypatch.setattr(seo_website_service.web_crawl, "assert_public_url", lambda url: None)
    grant_agent(business["business_id"], "seo_audit_optimization")

    create_resp = client.post("/api/agents/seo/websites", json={"url": "https://greenleaf.test"}, headers=business["headers"])
    website_id = create_resp.json()["id"]
    audit_resp = client.post(f"/api/agents/seo/websites/{website_id}/audits", headers=business["headers"])
    audit_id = audit_resp.json()["id"]

    resp = client.get(f"/api/agents/seo/audits/{audit_id}/performance", headers=business["headers"])

    assert resp.status_code == 200
    assert resp.json() == []
