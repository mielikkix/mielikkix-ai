"""QA 2026-10-02 (D8/E7): sitemap discovery beyond /sitemap.xml, and one SEO
website per site."""

from unittest.mock import AsyncMock

import pytest

from app.services import web_crawl


def _fake_sitemaps(available: dict):
    calls = []

    async def fetch(url, _depth=0):
        calls.append(url)
        return available.get(url, [])

    return fetch, calls


@pytest.mark.asyncio
async def test_sitemap_declared_in_robots_txt_is_used(monkeypatch):
    fetch, calls = _fake_sitemaps({"https://site.test/sitemap-index.xml": ["https://site.test/a", "https://site.test/b"]})
    monkeypatch.setattr(web_crawl, "fetch_sitemap_xml", fetch)
    monkeypatch.setattr(
        web_crawl, "fetch_robots_txt_text", AsyncMock(return_value="User-agent: *\nAllow: /\nSitemap: https://site.test/sitemap-index.xml\n")
    )

    assert await web_crawl.discover_sitemap_urls("https://site.test") == ["https://site.test/a", "https://site.test/b"]
    assert calls == ["https://site.test/sitemap-index.xml"]


@pytest.mark.asyncio
async def test_common_sitemap_names_are_tried_without_robots_hint(monkeypatch):
    fetch, calls = _fake_sitemaps({"https://site.test/sitemap-index.xml": ["https://site.test/a"]})
    monkeypatch.setattr(web_crawl, "fetch_sitemap_xml", fetch)
    monkeypatch.setattr(web_crawl, "fetch_robots_txt_text", AsyncMock(return_value=None))

    assert await web_crawl.discover_sitemap_urls("https://site.test") == ["https://site.test/a"]
    assert calls == [
        "https://site.test/sitemap.xml",
        "https://site.test/sitemap_index.xml",
        "https://site.test/sitemap-index.xml",
    ]


def test_same_seo_site_cannot_be_registered_twice(client, business, grant_agent, monkeypatch):
    grant_agent(business["business_id"], "seo_audit_optimization")
    monkeypatch.setattr(web_crawl, "assert_public_url", lambda url: None)

    first = client.post("/api/agents/seo/websites", json={"url": "https://mielikkix.ai/"}, headers=business["headers"])
    second = client.post("/api/agents/seo/websites", json={"url": "https://mielikkix.ai"}, headers=business["headers"])

    assert first.status_code in (200, 201), first.text
    assert second.status_code == 409
