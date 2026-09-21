"""Tests for the SEO Audit & Optimization agent's per-page structured
extraction (Stage 2 of apps/agents/seo-audit/CLAUDE.md). Deterministic
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
    assert result.images_missing_alt == 1  # logo.png has no alt attribute at all


@pytest.mark.asyncio
async def test_empty_alt_is_a_valid_decorative_marker_not_missing(monkeypatch):
    """Phase 2 fix: alt="" is the correct, intentional way to mark a
    decorative image (tells a screen reader to skip it) -- confirmed live
    against mielikkix.ai, whose flag icons and hero decoration all use it
    deliberately. Must never be counted the same as no alt attribute at all."""
    html = '<html><body><img src="/flag.svg" alt=""><img src="/icon.svg" alt=""></body></html>'
    _mock_fetch(monkeypatch, html)
    result = await seo_page_analyzer.analyze_page("https://greenleaf.test/")
    assert result.image_count == 2
    assert result.images_missing_alt == 0


@pytest.mark.asyncio
async def test_mix_of_empty_alt_and_truly_missing_alt(monkeypatch):
    html = (
        '<html><body>'
        '<img src="/decorative.svg" alt="">'
        '<img src="/informative.jpg" alt="A real description">'
        '<img src="/broken.jpg">'
        '</body></html>'
    )
    _mock_fetch(monkeypatch, html)
    result = await seo_page_analyzer.analyze_page("https://greenleaf.test/")
    assert result.image_count == 3
    assert result.images_missing_alt == 1  # only broken.jpg has no alt attribute


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
async def test_extracts_structured_data_types_from_valid_json_ld(monkeypatch):
    html = """
    <html><head>
    <script type="application/ld+json">{"@context": "https://schema.org", "@type": "Organization", "name": "Green Leaf"}</script>
    <script type="application/ld+json">{"@context": "https://schema.org", "@type": "WebSite"}</script>
    </head><body></body></html>
    """
    _mock_fetch(monkeypatch, html)
    result = await seo_page_analyzer.analyze_page("https://greenleaf.test/")
    assert set(result.structured_data_types) == {"Organization", "WebSite"}
    assert result.structured_data_invalid_count == 0


@pytest.mark.asyncio
async def test_structured_data_types_from_graph_wrapper(monkeypatch):
    html = """
    <html><head>
    <script type="application/ld+json">
    {"@context": "https://schema.org", "@graph": [{"@type": "Organization"}, {"@type": ["WebPage", "FAQPage"]}]}
    </script>
    </head><body></body></html>
    """
    _mock_fetch(monkeypatch, html)
    result = await seo_page_analyzer.analyze_page("https://greenleaf.test/")
    assert set(result.structured_data_types) == {"Organization", "WebPage", "FAQPage"}


@pytest.mark.asyncio
async def test_malformed_json_ld_is_counted_as_invalid_not_silently_skipped(monkeypatch):
    html = '<html><head><script type="application/ld+json">{not valid json,,,}</script></head><body></body></html>'
    _mock_fetch(monkeypatch, html)
    result = await seo_page_analyzer.analyze_page("https://greenleaf.test/")
    assert result.structured_data_invalid_count == 1
    assert result.structured_data_types == []


@pytest.mark.asyncio
async def test_page_with_no_structured_data_reports_empty_not_none(monkeypatch):
    _mock_fetch(monkeypatch, HTML)
    result = await seo_page_analyzer.analyze_page("https://greenleaf.test/")
    assert result.structured_data_types == []
    assert result.structured_data_invalid_count == 0


@pytest.mark.asyncio
async def test_html_lang_present_true_when_set(monkeypatch):
    _mock_fetch(monkeypatch, '<html lang="en"><body>ok</body></html>')
    result = await seo_page_analyzer.analyze_page("https://greenleaf.test/")
    assert result.html_lang_present is True


@pytest.mark.asyncio
async def test_html_lang_present_false_when_missing(monkeypatch):
    _mock_fetch(monkeypatch, "<html><body>ok</body></html>")
    result = await seo_page_analyzer.analyze_page("https://greenleaf.test/")
    assert result.html_lang_present is False


@pytest.mark.asyncio
async def test_html_lang_present_is_none_for_broken_page(monkeypatch):
    _mock_fetch(monkeypatch, "Not Found", status=404)
    result = await seo_page_analyzer.analyze_page("https://greenleaf.test/gone")
    assert result.html_lang_present is None


@pytest.mark.asyncio
async def test_heading_outline_records_levels_in_document_order(monkeypatch):
    html = "<html><body><h1>Title</h1><h2>Section</h2><h2>Section 2</h2><h4>Skip</h4></body></html>"
    _mock_fetch(monkeypatch, html)
    result = await seo_page_analyzer.analyze_page("https://greenleaf.test/")
    assert result.heading_outline == [1, 2, 2, 4]


@pytest.mark.asyncio
async def test_form_input_with_matching_label_for_is_not_flagged(monkeypatch):
    html = '<html><body><label for="email">Email</label><input type="email" id="email"></body></html>'
    _mock_fetch(monkeypatch, html)
    result = await seo_page_analyzer.analyze_page("https://greenleaf.test/")
    assert result.form_inputs_missing_label == 0


@pytest.mark.asyncio
async def test_form_input_wrapped_in_label_is_not_flagged(monkeypatch):
    html = "<html><body><label>Email <input type='email'></label></body></html>"
    _mock_fetch(monkeypatch, html)
    result = await seo_page_analyzer.analyze_page("https://greenleaf.test/")
    assert result.form_inputs_missing_label == 0


@pytest.mark.asyncio
async def test_form_input_with_aria_label_is_not_flagged(monkeypatch):
    html = '<html><body><input type="text" aria-label="Search"></body></html>'
    _mock_fetch(monkeypatch, html)
    result = await seo_page_analyzer.analyze_page("https://greenleaf.test/")
    assert result.form_inputs_missing_label == 0


@pytest.mark.asyncio
async def test_form_input_with_no_label_at_all_is_flagged(monkeypatch):
    html = '<html><body><input type="text"><textarea></textarea><select></select></body></html>'
    _mock_fetch(monkeypatch, html)
    result = await seo_page_analyzer.analyze_page("https://greenleaf.test/")
    assert result.form_inputs_missing_label == 3


@pytest.mark.asyncio
async def test_hidden_and_button_inputs_are_not_flagged(monkeypatch):
    """Hidden inputs and buttons don't need a label -- a hidden field has no
    visible UI, and a button's own text/value already serves that role."""
    html = '<html><body><input type="hidden" name="csrf"><input type="submit" value="Send"></body></html>'
    _mock_fetch(monkeypatch, html)
    result = await seo_page_analyzer.analyze_page("https://greenleaf.test/")
    assert result.form_inputs_missing_label == 0


@pytest.mark.asyncio
async def test_link_with_visible_text_is_not_flagged(monkeypatch):
    _mock_fetch(monkeypatch, HTML)
    result = await seo_page_analyzer.analyze_page("https://greenleaf.test/")
    assert result.links_missing_accessible_name == 0


@pytest.mark.asyncio
async def test_empty_link_with_no_accessible_name_is_flagged(monkeypatch):
    html = '<html><body><a href="/cart"><img src="/cart-icon.png"></a></body></html>'
    _mock_fetch(monkeypatch, html)
    result = await seo_page_analyzer.analyze_page("https://greenleaf.test/")
    assert result.links_missing_accessible_name == 1


@pytest.mark.asyncio
async def test_empty_link_with_aria_label_is_not_flagged(monkeypatch):
    html = '<html><body><a href="/cart" aria-label="View cart"><img src="/cart-icon.png"></a></body></html>'
    _mock_fetch(monkeypatch, html)
    result = await seo_page_analyzer.analyze_page("https://greenleaf.test/")
    assert result.links_missing_accessible_name == 0


@pytest.mark.asyncio
async def test_empty_link_with_alt_text_image_is_not_flagged(monkeypatch):
    html = '<html><body><a href="/cart"><img src="/cart-icon.png" alt="View cart"></a></body></html>'
    _mock_fetch(monkeypatch, html)
    result = await seo_page_analyzer.analyze_page("https://greenleaf.test/")
    assert result.links_missing_accessible_name == 0


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
