"""Tests for the full-site knowledge-base crawl (app/services/document_service.py
discovery helpers + crawl_and_ingest_website, and POST /api/documents/from-website).

Network calls are always mocked -- no real HTTP requests happen in this suite.
"""
import httpx
import pytest

from app.models.document import Document
from app.services import document_service
from app.api import documents as documents_api


# ---------------------------------------------------------------------------
# Fake httpx transport
# ---------------------------------------------------------------------------

class _FakeAsyncClient:
    """Drop-in stand-in for httpx.AsyncClient, routing GETs by exact URL or
    by a substring match, so discovery code under test never hits the network."""

    def __init__(self, responses, *args, **kwargs):
        self._responses = responses

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False

    async def get(self, url, **kwargs):
        for key, resp in self._responses.items():
            if key in url:
                return resp
        return httpx.Response(404, request=httpx.Request("GET", url))


def _patch_client(monkeypatch, responses):
    monkeypatch.setattr(document_service.httpx, "AsyncClient", lambda *a, **k: _FakeAsyncClient(responses))


def _xml_response(body: str) -> httpx.Response:
    return httpx.Response(200, content=body.encode(), request=httpx.Request("GET", "https://x.test/sitemap.xml"))


SITEMAP = """<?xml version="1.0" encoding="UTF-8"?>
<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
  <url><loc>https://greenleaf.test/</loc></url>
  <url><loc>https://greenleaf.test/about</loc></url>
  <url><loc>https://greenleaf.test/menu</loc></url>
</urlset>"""

SITEMAP_INDEX = """<?xml version="1.0" encoding="UTF-8"?>
<sitemapindex xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
  <sitemap><loc>https://greenleaf.test/sitemap-pages.xml</loc></sitemap>
  <sitemap><loc>https://greenleaf.test/sitemap-posts.xml</loc></sitemap>
</sitemapindex>"""

NESTED_PAGES = """<?xml version="1.0" encoding="UTF-8"?>
<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
  <url><loc>https://greenleaf.test/page-a</loc></url>
</urlset>"""

NESTED_POSTS = """<?xml version="1.0" encoding="UTF-8"?>
<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
  <url><loc>https://greenleaf.test/post-a</loc></url>
</urlset>"""


# ---------------------------------------------------------------------------
# Sitemap discovery
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_sitemap_discovery_parses_loc_entries(monkeypatch):
    _patch_client(monkeypatch, {"sitemap.xml": _xml_response(SITEMAP)})
    urls = await document_service._discover_sitemap_urls("https://greenleaf.test")
    assert urls == [
        "https://greenleaf.test/",
        "https://greenleaf.test/about",
        "https://greenleaf.test/menu",
    ]


@pytest.mark.asyncio
async def test_sitemap_index_follows_nested_sitemaps(monkeypatch):
    _patch_client(monkeypatch, {
        "sitemap.xml": _xml_response(SITEMAP_INDEX),
        "sitemap-pages.xml": _xml_response(NESTED_PAGES),
        "sitemap-posts.xml": _xml_response(NESTED_POSTS),
    })
    urls = await document_service._discover_sitemap_urls("https://greenleaf.test")
    assert set(urls) == {"https://greenleaf.test/page-a", "https://greenleaf.test/post-a"}


@pytest.mark.asyncio
async def test_missing_sitemap_returns_empty(monkeypatch):
    _patch_client(monkeypatch, {})  # everything 404s
    urls = await document_service._discover_sitemap_urls("https://greenleaf.test")
    assert urls == []


# ---------------------------------------------------------------------------
# robots.txt filtering + MAX_CRAWL_PAGES cap, via discover_website_pages
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_robots_disallow_filters_urls(monkeypatch):
    monkeypatch.setattr(document_service, "_assert_public_url", lambda url: None)  # not testing SSRF/DNS here
    sitemap = """<?xml version="1.0"?>
    <urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
      <url><loc>https://greenleaf.test/about</loc></url>
      <url><loc>https://greenleaf.test/admin</loc></url>
    </urlset>"""
    robots = "User-agent: *\nDisallow: /admin\n"
    _patch_client(monkeypatch, {
        "sitemap.xml": _xml_response(sitemap),
        "robots.txt": httpx.Response(200, text=robots, request=httpx.Request("GET", "https://greenleaf.test/robots.txt")),
    })
    pages = await document_service.discover_website_pages("https://greenleaf.test")
    assert pages == ["https://greenleaf.test/about"]


@pytest.mark.asyncio
async def test_discovery_capped_at_max_crawl_pages(monkeypatch):
    monkeypatch.setattr(document_service, "_assert_public_url", lambda url: None)  # not testing SSRF/DNS here
    many_urls = "\n".join(
        f"<url><loc>https://greenleaf.test/page-{i}</loc></url>" for i in range(document_service.MAX_CRAWL_PAGES + 10)
    )
    sitemap = f'<?xml version="1.0"?><urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">{many_urls}</urlset>'
    _patch_client(monkeypatch, {"sitemap.xml": _xml_response(sitemap)})  # no robots.txt -> allow all
    pages = await document_service.discover_website_pages("https://greenleaf.test")
    assert len(pages) == document_service.MAX_CRAWL_PAGES


# ---------------------------------------------------------------------------
# POST /api/documents/from-website
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_from_website_400_when_nothing_discovered(client, business, monkeypatch):
    async def fake_discover(url):
        return []

    monkeypatch.setattr(documents_api, "discover_website_pages", fake_discover)
    resp = client.post("/api/documents/from-website", headers=business["headers"], json={"url": "https://greenleaf.test"})
    assert resp.status_code == 400


def test_from_website_402_when_already_at_document_cap(client, business, db_session):
    # Free plan caps at 2 document uploads.
    for i in range(2):
        db_session.add(Document(
            business_id=business["business_id"], filename=f"doc-{i}.txt", file_url="x",
            file_type="txt", status="embedded",
        ))
    db_session.commit()

    resp = client.post("/api/documents/from-website", headers=business["headers"], json={"url": "https://greenleaf.test"})
    assert resp.status_code == 402


@pytest.mark.asyncio
async def test_from_website_trims_queued_to_remaining_capacity(client, business, db_session, monkeypatch):
    # Free plan caps at 2 -- one slot already used, one remaining.
    db_session.add(Document(
        business_id=business["business_id"], filename="existing.txt", file_url="x",
        file_type="txt", status="embedded",
    ))
    db_session.commit()

    async def fake_discover(url):
        return [f"https://greenleaf.test/page-{i}" for i in range(5)]

    async def fake_crawl(*args, **kwargs):
        return None  # background task -- must not actually run network code in this test

    monkeypatch.setattr(documents_api, "discover_website_pages", fake_discover)
    monkeypatch.setattr(documents_api, "crawl_and_ingest_website", fake_crawl)

    resp = client.post("/api/documents/from-website", headers=business["headers"], json={"url": "https://greenleaf.test"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["discovered"] == 5
    assert body["queued"] == 1


def test_non_admin_business_owner_can_still_crawl_their_own_site(client, business, monkeypatch):
    # Sanity check: no admin gating on this endpoint -- any authenticated
    # business owner can crawl their own site.
    async def fake_discover(url):
        return ["https://greenleaf.test/only-page"]

    async def fake_crawl(*args, **kwargs):
        return None

    monkeypatch.setattr(documents_api, "discover_website_pages", fake_discover)
    monkeypatch.setattr(documents_api, "crawl_and_ingest_website", fake_crawl)

    resp = client.post("/api/documents/from-website", headers=business["headers"], json={"url": "https://greenleaf.test"})
    assert resp.status_code == 200
    assert resp.json()["queued"] == 1


# ---------------------------------------------------------------------------
# crawl_and_ingest_website (the background worker itself)
# ---------------------------------------------------------------------------

@pytest.fixture()
def use_test_db_for_crawl(monkeypatch, db_session):
    """crawl_and_ingest_website opens its own SessionLocal() since it runs
    after the request's session is closed -- redirect that to the test's
    isolated session so these tests hit the test schema, not the dev DB."""
    monkeypatch.setattr(document_service, "SessionLocal", lambda: db_session)


@pytest.mark.asyncio
async def test_crawl_skips_url_that_already_exists_as_document(client, business, db_session, monkeypatch, use_test_db_for_crawl):
    existing_url = "https://greenleaf.test/about"
    db_session.add(Document(
        business_id=business["business_id"], filename=existing_url, file_url=existing_url,
        file_type="url", status="embedded",
    ))
    db_session.commit()

    calls = []

    async def fake_ingest_url(db, business_id, user_id, url):
        calls.append(url)

    monkeypatch.setattr(document_service, "ingest_url", fake_ingest_url)
    await document_service.crawl_and_ingest_website(
        business["business_id"], business["business_id"], [existing_url, "https://greenleaf.test/menu"]
    )
    assert calls == ["https://greenleaf.test/menu"]


@pytest.mark.asyncio
async def test_crawl_continues_after_one_page_fails(business, db_session, monkeypatch, use_test_db_for_crawl):
    async def flaky_ingest_url(db, business_id, user_id, url):
        if "bad" in url:
            raise RuntimeError("simulated fetch failure")
        db.add(Document(business_id=business_id, filename=url, file_url=url, file_type="url", status="embedded"))
        db.commit()

    monkeypatch.setattr(document_service, "ingest_url", flaky_ingest_url)
    urls = ["https://greenleaf.test/a", "https://greenleaf.test/bad", "https://greenleaf.test/c"]
    await document_service.crawl_and_ingest_website(business["business_id"], business["business_id"], urls)

    saved = db_session.query(Document).filter(Document.business_id == business["business_id"]).all()
    assert {d.filename for d in saved} == {"https://greenleaf.test/a", "https://greenleaf.test/c"}


@pytest.mark.asyncio
async def test_crawl_stops_once_plan_document_cap_is_reached(business, db_session, monkeypatch, use_test_db_for_crawl):
    async def fake_ingest_url(db, business_id, user_id, url):
        db.add(Document(business_id=business_id, filename=url, file_url=url, file_type="url", status="embedded"))
        db.commit()

    monkeypatch.setattr(document_service, "ingest_url", fake_ingest_url)
    urls = [f"https://greenleaf.test/page-{i}" for i in range(5)]
    await document_service.crawl_and_ingest_website(business["business_id"], business["business_id"], urls)

    # Free plan caps at 2 document uploads -- the crawl must stop there even
    # though 5 URLs were queued.
    saved = db_session.query(Document).filter(Document.business_id == business["business_id"]).all()
    assert len(saved) == 2
