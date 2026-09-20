"""Tests for SEO audit runs (Stage 2 of apps/agents/seo-audit/CLAUDE.md
-- crawl + per-page structured extraction). The crawler/analyzer layers
have their own dedicated tests (test_web_crawl.py, test_seo_page_analyzer.py);
this file covers create_audit/run_audit orchestration and the HTTP surface.
"""
from unittest.mock import AsyncMock

import pytest

from app.models.seo_audit import SeoAudit, SeoCrawledPage
from app.models.seo_website import SeoWebsite
from app.services import seo_audit_service, seo_page_analyzer, seo_website_service, web_crawl


def _entitle(business, grant_agent):
    grant_agent(business["business_id"], "seo_audit_optimization")


def _stub_public_url(monkeypatch):
    monkeypatch.setattr(seo_website_service.web_crawl, "assert_public_url", lambda url: None)


def _make_website(client, headers) -> str:
    resp = client.post("/api/agents/seo/websites", json={"url": "https://greenleaf.test"}, headers=headers)
    assert resp.status_code == 200, resp.text
    return resp.json()["id"]


def _fake_analysis(url: str, **overrides) -> seo_page_analyzer.PageAnalysis:
    defaults = dict(
        url=url, http_status=200, title="A title", meta_description="A description",
        h1_count=1, word_count=120, canonical_url=url, meta_robots=None, x_robots_tag=None,
        is_indexable=True, redirect_chain=[url], internal_link_count=3, image_count=2, images_missing_alt=1,
    )
    defaults.update(overrides)
    return seo_page_analyzer.PageAnalysis(**defaults)


def test_start_audit_requires_entitlement(client, business):
    resp = client.post(
        "/api/agents/seo/websites/00000000-0000-0000-0000-000000000000/audits", headers=business["headers"]
    )
    assert resp.status_code == 403


def test_start_audit_404s_for_unknown_website(client, business, grant_agent):
    _entitle(business, grant_agent)
    resp = client.post(
        "/api/agents/seo/websites/00000000-0000-0000-0000-000000000000/audits", headers=business["headers"]
    )
    assert resp.status_code == 404


def test_start_audit_creates_a_pending_audit(client, business, grant_agent, monkeypatch):
    _entitle(business, grant_agent)
    _stub_public_url(monkeypatch)
    website_id = _make_website(client, business["headers"])

    resp = client.post(f"/api/agents/seo/websites/{website_id}/audits", headers=business["headers"])

    assert resp.status_code == 200
    body = resp.json()
    assert body["website_id"] == website_id
    assert body["status"] == "pending"
    assert body["pages_crawled"] == 0


def test_list_audits_scoped_to_website_and_business(client, business, signup, grant_agent, monkeypatch):
    _entitle(business, grant_agent)
    other = signup()
    grant_agent(other["business_id"], "seo_audit_optimization")
    _stub_public_url(monkeypatch)

    website_id = _make_website(client, business["headers"])
    client.post(f"/api/agents/seo/websites/{website_id}/audits", headers=business["headers"])

    other_website_id = _make_website(client, other["headers"])
    client.post(f"/api/agents/seo/websites/{other_website_id}/audits", headers=other["headers"])

    resp = client.get(f"/api/agents/seo/websites/{website_id}/audits", headers=business["headers"])
    assert resp.status_code == 200
    assert len(resp.json()) == 1


def test_get_unknown_audit_404s(client, business, grant_agent):
    _entitle(business, grant_agent)
    resp = client.get("/api/agents/seo/audits/00000000-0000-0000-0000-000000000000", headers=business["headers"])
    assert resp.status_code == 404


def test_cannot_get_another_businesss_audit(client, business, signup, grant_agent, monkeypatch, db_session):
    _entitle(business, grant_agent)
    other = signup()
    grant_agent(other["business_id"], "seo_audit_optimization")
    _stub_public_url(monkeypatch)

    other_website_id = _make_website(client, other["headers"])
    create_resp = client.post(f"/api/agents/seo/websites/{other_website_id}/audits", headers=other["headers"])
    audit_id = create_resp.json()["id"]

    resp = client.get(f"/api/agents/seo/audits/{audit_id}", headers=business["headers"])
    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# run_audit -- the background worker itself
# ---------------------------------------------------------------------------

@pytest.fixture()
def use_test_db_for_audit(monkeypatch, db_session):
    monkeypatch.setattr(seo_audit_service, "SessionLocal", lambda: db_session)


@pytest.mark.asyncio
async def test_run_audit_crawls_and_stores_pages(business, db_session, monkeypatch, use_test_db_for_audit):
    website = SeoWebsite(business_id=business["business_id"], url="https://greenleaf.test", crawl_tier="starter")
    db_session.add(website)
    db_session.commit()
    audit = seo_audit_service.create_audit(db_session, website)

    urls = ["https://greenleaf.test/", "https://greenleaf.test/menu"]
    monkeypatch.setattr(web_crawl, "discover_website_pages", AsyncMock(return_value=urls))
    monkeypatch.setattr(seo_page_analyzer, "analyze_page", AsyncMock(side_effect=lambda u: _fake_analysis(u)))

    audit_id = audit.id
    await seo_audit_service.run_audit(str(audit_id))

    # run_audit closes its own session when it's done (it opens SessionLocal()
    # since it runs after the request's session would normally be closed --
    # see the module docstring) -- re-query fresh rather than refresh() a
    # pre-existing instance, same pattern test_website_crawl.py's own
    # crawl_and_ingest_website tests use for the same reason.
    audit = db_session.query(SeoAudit).filter(SeoAudit.id == audit_id).first()
    assert audit.status == "completed"
    assert audit.pages_discovered == 2
    assert audit.pages_crawled == 2
    assert audit.pages_blocked == 0
    assert audit.started_at is not None
    assert audit.completed_at is not None

    pages = db_session.query(SeoCrawledPage).filter(SeoCrawledPage.audit_id == audit_id).all()
    assert {p.url for p in pages} == set(urls)
    assert all(p.title == "A title" for p in pages)


@pytest.mark.asyncio
async def test_run_audit_counts_a_failed_page_as_blocked_not_aborted(business, db_session, monkeypatch, use_test_db_for_audit):
    website = SeoWebsite(business_id=business["business_id"], url="https://greenleaf.test", crawl_tier="starter")
    db_session.add(website)
    db_session.commit()
    audit = seo_audit_service.create_audit(db_session, website)

    urls = ["https://greenleaf.test/good", "https://greenleaf.test/bad"]
    monkeypatch.setattr(web_crawl, "discover_website_pages", AsyncMock(return_value=urls))

    async def flaky_analyze(url):
        if "bad" in url:
            raise RuntimeError("simulated fetch failure")
        return _fake_analysis(url)

    monkeypatch.setattr(seo_page_analyzer, "analyze_page", flaky_analyze)

    audit_id = audit.id
    await seo_audit_service.run_audit(str(audit_id))

    audit = db_session.query(SeoAudit).filter(SeoAudit.id == audit_id).first()
    assert audit.status == "completed"
    assert audit.pages_crawled == 1
    assert audit.pages_blocked == 1

    pages = db_session.query(SeoCrawledPage).filter(SeoCrawledPage.audit_id == audit_id).all()
    assert [p.url for p in pages] == ["https://greenleaf.test/good"]


@pytest.mark.asyncio
async def test_run_audit_respects_crawl_tier_page_limit(business, db_session, monkeypatch, use_test_db_for_audit):
    website = SeoWebsite(business_id=business["business_id"], url="https://greenleaf.test", crawl_tier="advanced")
    db_session.add(website)
    db_session.commit()
    audit = seo_audit_service.create_audit(db_session, website)

    discover_mock = AsyncMock(return_value=[])
    monkeypatch.setattr(web_crawl, "discover_website_pages", discover_mock)

    await seo_audit_service.run_audit(str(audit.id))

    discover_mock.assert_called_once_with("https://greenleaf.test", max_pages=500)


def test_deleting_a_website_cascades_to_its_audits(business, db_session):
    """seo_audits.website_id is ON DELETE CASCADE (see the migration) --
    deleting a website must not leave orphaned audit rows behind, and also
    means run_audit's own "website vanished mid-run" guard can only ever
    be reached by a genuinely concurrent delete, not a stale row."""
    website = SeoWebsite(business_id=business["business_id"], url="https://greenleaf.test", crawl_tier="starter")
    db_session.add(website)
    db_session.commit()
    audit = seo_audit_service.create_audit(db_session, website)
    audit_id = audit.id

    db_session.delete(website)
    db_session.commit()

    assert db_session.query(SeoAudit).filter(SeoAudit.id == audit_id).first() is None


def test_list_audit_pages(client, business, grant_agent, monkeypatch, db_session):
    _entitle(business, grant_agent)
    _stub_public_url(monkeypatch)
    website_id = _make_website(client, business["headers"])
    create_resp = client.post(f"/api/agents/seo/websites/{website_id}/audits", headers=business["headers"])
    audit_id = create_resp.json()["id"]

    db_session.add(SeoCrawledPage(audit_id=audit_id, url="https://greenleaf.test/", title="Home", h1_count=1))
    db_session.commit()

    resp = client.get(f"/api/agents/seo/audits/{audit_id}/pages", headers=business["headers"])
    assert resp.status_code == 200
    body = resp.json()
    assert len(body) == 1
    assert body[0]["url"] == "https://greenleaf.test/"
    assert body[0]["title"] == "Home"
