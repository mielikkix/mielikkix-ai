"""Tests for the shared crawler layer (app/services/web_crawl.py) --
extracted from document_service.py in Stage 2 of apps/agents/
seo-copywriter/CLAUDE.md so both document ingestion and the SEO Audit &
Optimization agent's crawler share one hardened fetch/SSRF/robots/sitemap
implementation instead of two. Network calls are always mocked -- no real
HTTP requests happen in this suite.
"""
import httpx
import pytest
from fastapi import HTTPException

from app.services import web_crawl


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
    monkeypatch.setattr(web_crawl.httpx, "AsyncClient", lambda *a, **k: _FakeAsyncClient(responses))


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
# SSRF guard (assert_public_url) -- no prior dedicated coverage existed
# ---------------------------------------------------------------------------

def test_rejects_non_http_scheme():
    with pytest.raises(Exception) as exc:
        web_crawl.assert_public_url("ftp://example.com")
    assert exc.value.status_code == 400


def test_rejects_url_with_no_hostname():
    with pytest.raises(Exception) as exc:
        web_crawl.assert_public_url("https:///path")
    assert exc.value.status_code == 400


def test_rejects_unresolvable_host(monkeypatch):
    import socket

    def fake_gethostbyname(host):
        raise socket.gaierror("not found")

    monkeypatch.setattr(web_crawl.socket, "gethostbyname", fake_gethostbyname)
    with pytest.raises(Exception) as exc:
        web_crawl.assert_public_url("https://nonexistent.invalid")
    assert exc.value.status_code == 400


@pytest.mark.parametrize("ip", ["127.0.0.1", "10.0.0.5", "169.254.169.254", "192.168.1.1"])
def test_rejects_private_and_link_local_ips(monkeypatch, ip):
    monkeypatch.setattr(web_crawl.socket, "gethostbyname", lambda host: ip)
    with pytest.raises(Exception) as exc:
        web_crawl.assert_public_url("https://internal.example")
    assert exc.value.status_code == 400


def test_allows_a_genuine_public_ip(monkeypatch):
    monkeypatch.setattr(web_crawl.socket, "gethostbyname", lambda host: "93.184.216.34")
    web_crawl.assert_public_url("https://example.com")  # must not raise


# ---------------------------------------------------------------------------
# Sitemap discovery
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_sitemap_discovery_parses_loc_entries(monkeypatch):
    _patch_client(monkeypatch, {"sitemap.xml": _xml_response(SITEMAP)})
    urls = await web_crawl.discover_sitemap_urls("https://greenleaf.test")
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
    urls = await web_crawl.discover_sitemap_urls("https://greenleaf.test")
    assert set(urls) == {"https://greenleaf.test/page-a", "https://greenleaf.test/post-a"}


@pytest.mark.asyncio
async def test_missing_sitemap_returns_empty(monkeypatch):
    _patch_client(monkeypatch, {})  # everything 404s
    urls = await web_crawl.discover_sitemap_urls("https://greenleaf.test")
    assert urls == []


@pytest.mark.asyncio
async def test_malformed_sitemap_xml_returns_empty_not_raises(monkeypatch):
    _patch_client(monkeypatch, {"sitemap.xml": _xml_response("<not><valid xml")})
    urls = await web_crawl.discover_sitemap_urls("https://greenleaf.test")
    assert urls == []


# ---------------------------------------------------------------------------
# robots.txt filtering + page cap, via discover_website_pages
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_robots_disallow_filters_urls(monkeypatch):
    monkeypatch.setattr(web_crawl, "assert_public_url", lambda url: None)  # not testing SSRF/DNS here
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
    pages = await web_crawl.discover_website_pages("https://greenleaf.test")
    assert pages == ["https://greenleaf.test/about"]


@pytest.mark.asyncio
async def test_missing_robots_txt_allows_everything(monkeypatch):
    monkeypatch.setattr(web_crawl, "assert_public_url", lambda url: None)
    sitemap = """<?xml version="1.0"?>
    <urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
      <url><loc>https://greenleaf.test/about</loc></url>
    </urlset>"""
    _patch_client(monkeypatch, {"sitemap.xml": _xml_response(sitemap)})  # robots.txt 404s
    pages = await web_crawl.discover_website_pages("https://greenleaf.test")
    assert pages == ["https://greenleaf.test/about"]


@pytest.mark.asyncio
async def test_discovery_capped_at_max_crawl_pages(monkeypatch):
    monkeypatch.setattr(web_crawl, "assert_public_url", lambda url: None)  # not testing SSRF/DNS here
    many_urls = "\n".join(
        f"<url><loc>https://greenleaf.test/page-{i}</loc></url>" for i in range(web_crawl.MAX_CRAWL_PAGES + 10)
    )
    sitemap = f'<?xml version="1.0"?><urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">{many_urls}</urlset>'
    _patch_client(monkeypatch, {"sitemap.xml": _xml_response(sitemap)})  # no robots.txt -> allow all
    pages = await web_crawl.discover_website_pages("https://greenleaf.test")
    assert len(pages) == web_crawl.MAX_CRAWL_PAGES


@pytest.mark.asyncio
async def test_discovery_respects_a_smaller_custom_page_limit(monkeypatch):
    """SeoWebsite.crawl_tier (see models/seo_website.py) passes a caller-
    specific max_pages below web_crawl's own MAX_CRAWL_PAGES ceiling."""
    monkeypatch.setattr(web_crawl, "assert_public_url", lambda url: None)
    many_urls = "\n".join(f"<url><loc>https://greenleaf.test/page-{i}</loc></url>" for i in range(10))
    sitemap = f'<?xml version="1.0"?><urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">{many_urls}</urlset>'
    _patch_client(monkeypatch, {"sitemap.xml": _xml_response(sitemap)})
    pages = await web_crawl.discover_website_pages("https://greenleaf.test", max_pages=3)
    assert len(pages) == 3


# ---------------------------------------------------------------------------
# fetch_with_redirects
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_fetch_with_redirects_follows_a_single_hop(monkeypatch):
    monkeypatch.setattr(web_crawl, "assert_public_url", lambda url: None)

    class _RedirectClient:
        def __init__(self, *a, **k):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *exc):
            return False

        async def get(self, url, **kwargs):
            if url == "https://greenleaf.test/old":
                return httpx.Response(
                    301, headers={"location": "https://greenleaf.test/new"},
                    request=httpx.Request("GET", url),
                )
            return httpx.Response(200, text="hello", request=httpx.Request("GET", url))

    monkeypatch.setattr(web_crawl.httpx, "AsyncClient", lambda *a, **k: _RedirectClient())

    resp, chain = await web_crawl.fetch_with_redirects("https://greenleaf.test/old")
    assert resp.status_code == 200
    assert chain == ["https://greenleaf.test/old", "https://greenleaf.test/new"]


@pytest.mark.asyncio
async def test_fetch_with_redirects_rejects_a_redirect_to_a_private_ip(monkeypatch):
    """The whole point of re-validating every hop: a public URL redirecting
    to an internal address must not be followed."""
    class _RedirectClient:
        def __init__(self, *a, **k):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *exc):
            return False

        async def get(self, url, **kwargs):
            return httpx.Response(
                302, headers={"location": "https://greenleaf.test/internal-redirect-target"},
                request=httpx.Request("GET", url),
            )

    def fake_assert_public_url(url):
        if url == "https://greenleaf.test/internal-redirect-target":
            raise HTTPException(status_code=400, detail="blocked")

    monkeypatch.setattr(web_crawl, "assert_public_url", fake_assert_public_url)
    monkeypatch.setattr(web_crawl.httpx, "AsyncClient", lambda *a, **k: _RedirectClient())

    with pytest.raises(HTTPException) as exc:
        await web_crawl.fetch_with_redirects("https://greenleaf.test/start")
    assert exc.value.status_code == 400


@pytest.mark.asyncio
async def test_fetch_with_redirects_too_many_hops_raises(monkeypatch):
    monkeypatch.setattr(web_crawl, "assert_public_url", lambda url: None)

    class _LoopingClient:
        def __init__(self, *a, **k):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *exc):
            return False

        async def get(self, url, **kwargs):
            return httpx.Response(302, headers={"location": "https://greenleaf.test/loop"}, request=httpx.Request("GET", url))

    monkeypatch.setattr(web_crawl.httpx, "AsyncClient", lambda *a, **k: _LoopingClient())

    with pytest.raises(HTTPException) as exc:
        await web_crawl.fetch_with_redirects("https://greenleaf.test/start", max_redirects=3)
    assert exc.value.status_code == 400


@pytest.mark.asyncio
async def test_fetch_with_redirects_rejects_oversized_response(monkeypatch):
    monkeypatch.setattr(web_crawl, "assert_public_url", lambda url: None)

    class _BigClient:
        def __init__(self, *a, **k):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *exc):
            return False

        async def get(self, url, **kwargs):
            return httpx.Response(200, content=b"x" * 100, request=httpx.Request("GET", url))

    monkeypatch.setattr(web_crawl.httpx, "AsyncClient", lambda *a, **k: _BigClient())

    with pytest.raises(HTTPException) as exc:
        await web_crawl.fetch_with_redirects("https://greenleaf.test/big", max_bytes=10)
    assert exc.value.status_code == 400
