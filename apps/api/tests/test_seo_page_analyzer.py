"""Tests for the SEO Audit & Optimization agent's per-page structured
extraction (Stage 2 of apps/agents/seo-copywriter/CLAUDE.md). Deterministic
only -- every assertion here traces back to real HTML/headers in the fake
response, never an LLM guess (see that CLAUDE.md's "no fake numbers, no
fabricated findings" rule).
"""
import httpx
import pytest

from app.services import seo_page_analyzer, web_crawl


def _mock_fetch(monkeypatch, html: str, status: int = 200, headers: dict | None = None, chain=None):
    resp = httpx.Response(
        status,
        text=html,
        headers={"content-type": "text/html", **(headers or {})},
        request=httpx.Request("GET", "https://greenleaf.test/page"),
    )

    async def fake_fetch(url, max_bytes=None, max_redirects=5):
        return resp, chain or [url]

    monkeypatch.setattr(seo_page_analyzer.web_crawl, "fetch_with_redirects", fake_fetch)


HTML = """
<html>
<head>
  <title>Green Leaf Cafe | Home</title>
  <meta name="description" content="Organic coffee and pastries in downtown Oslo.">
  <link rel="canonical" href="https://greenleaf.test/">
</head>
<body>
  <h1>Welcome to Green Leaf</h1>
  <p>We serve organic coffee and fresh pastries every day.</p>
  <a href="/menu">Menu</a>
  <a href="https://external.example/partner">Partner</a>
  <img src="/hero.jpg" alt="Cafe interior">
  <img src="/logo.png">
</body>
</html>
"""


@pytest.mark.asyncio
async def test_extracts_title_meta_canonical_and_headings(monkeypatch):
    _mock_fetch(monkeypatch, HTML)
    result = await seo_page_analyzer.analyze_page("https://greenleaf.test/")

    assert result.title == "Green Leaf Cafe | Home"
    assert result.meta_description == "Organic coffee and pastries in downtown Oslo."
    assert result.canonical_url == "https://greenleaf.test/"
    assert result.h1_count == 1
    assert result.word_count > 0


@pytest.mark.asyncio
async def test_counts_internal_links_not_external(monkeypatch):
    _mock_fetch(monkeypatch, HTML)
    result = await seo_page_analyzer.analyze_page("https://greenleaf.test/")
    assert result.internal_link_count == 1  # /menu only, not the external.example link


@pytest.mark.asyncio
async def test_counts_images_missing_alt(monkeypatch):
    _mock_fetch(monkeypatch, HTML)
    result = await seo_page_analyzer.analyze_page("https://greenleaf.test/")
    assert result.image_count == 2
    assert result.images_missing_alt == 1  # logo.png has no alt


@pytest.mark.asyncio
async def test_missing_h1_is_reported_as_zero(monkeypatch):
    _mock_fetch(monkeypatch, "<html><head><title>No heading</title></head><body>No H1 here.</body></html>")
    result = await seo_page_analyzer.analyze_page("https://greenleaf.test/no-h1")
    assert result.h1_count == 0


@pytest.mark.asyncio
async def test_multiple_h1s_are_counted_not_flagged(monkeypatch):
    """Deterministic counting only -- this agent's CLAUDE.md explicitly
    says not to auto-flag multiple H1s as always wrong; that judgment
    belongs to a later analyzer stage, not this extraction layer."""
    _mock_fetch(monkeypatch, "<html><body><h1>One</h1><h1>Two</h1></body></html>")
    result = await seo_page_analyzer.analyze_page("https://greenleaf.test/two-h1")
    assert result.h1_count == 2


@pytest.mark.asyncio
async def test_meta_robots_noindex_marks_page_not_indexable(monkeypatch):
    html = '<html><head><meta name="robots" content="noindex, nofollow"></head><body></body></html>'
    _mock_fetch(monkeypatch, html)
    result = await seo_page_analyzer.analyze_page("https://greenleaf.test/private")
    assert result.meta_robots == "noindex, nofollow"
    assert result.is_indexable is False


@pytest.mark.asyncio
async def test_x_robots_tag_noindex_marks_page_not_indexable(monkeypatch):
    _mock_fetch(monkeypatch, "<html><body>ok</body></html>", headers={"x-robots-tag": "noindex"})
    result = await seo_page_analyzer.analyze_page("https://greenleaf.test/private-header")
    assert result.is_indexable is False


@pytest.mark.asyncio
async def test_page_with_no_robots_signal_is_indexable(monkeypatch):
    _mock_fetch(monkeypatch, HTML)
    result = await seo_page_analyzer.analyze_page("https://greenleaf.test/")
    assert result.is_indexable is True


@pytest.mark.asyncio
async def test_broken_page_records_status_without_raising(monkeypatch):
    _mock_fetch(monkeypatch, "Not Found", status=404)
    result = await seo_page_analyzer.analyze_page("https://greenleaf.test/gone")
    assert result.http_status == 404
    assert result.title is None
    assert result.h1_count == 0


@pytest.mark.asyncio
async def test_redirect_chain_is_recorded(monkeypatch):
    _mock_fetch(monkeypatch, HTML, chain=["https://greenleaf.test/old", "https://greenleaf.test/"])
    result = await seo_page_analyzer.analyze_page("https://greenleaf.test/old")
    assert result.redirect_chain == ["https://greenleaf.test/old", "https://greenleaf.test/"]


@pytest.mark.asyncio
async def test_broken_page_has_no_content_hash(monkeypatch):
    _mock_fetch(monkeypatch, "Not Found", status=404)
    result = await seo_page_analyzer.analyze_page("https://greenleaf.test/gone")
    assert result.content_hash is None


@pytest.mark.asyncio
async def test_identical_pages_produce_the_same_content_hash(monkeypatch):
    _mock_fetch(monkeypatch, HTML)
    a = await seo_page_analyzer.analyze_page("https://greenleaf.test/a")
    _mock_fetch(monkeypatch, HTML)
    b = await seo_page_analyzer.analyze_page("https://greenleaf.test/b")
    assert a.content_hash is not None
    assert a.content_hash == b.content_hash


@pytest.mark.asyncio
async def test_different_content_produces_a_different_hash(monkeypatch):
    _mock_fetch(monkeypatch, HTML)
    a = await seo_page_analyzer.analyze_page("https://greenleaf.test/a")
    _mock_fetch(monkeypatch, "<html><body><h1>Totally different page</h1><p>Unrelated content.</p></body></html>")
    b = await seo_page_analyzer.analyze_page("https://greenleaf.test/b")
    assert a.content_hash != b.content_hash


@pytest.mark.asyncio
async def test_nav_and_footer_boilerplate_does_not_count_toward_word_count(monkeypatch):
    html = (
        "<html><body>"
        "<nav>Home About Contact Menu Login Sign up Blog Careers Support</nav>"
        "<footer>Copyright 2026 Company All rights reserved Privacy Terms</footer>"
        "<h1>Real content</h1><p>Just three real words here.</p>"
        "</body></html>"
    )
    _mock_fetch(monkeypatch, html)
    result = await seo_page_analyzer.analyze_page("https://greenleaf.test/thin")
    # "Real content Just three real words here." = 7 words -- nav/footer text excluded
    assert result.word_count == 7
