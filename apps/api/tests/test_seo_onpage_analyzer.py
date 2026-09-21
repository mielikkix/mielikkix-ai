"""Tests for the Stage 4 on-page analyzer (app/services/seo_onpage_analyzer.py)
-- pure functions, no DB/network. Every assertion traces back to a specific
fake crawled-page object, never an invented number.
"""
from types import SimpleNamespace

from app.services import seo_onpage_analyzer as opa


def _page(**overrides):
    defaults = dict(
        url="https://greenleaf.test/",
        http_status=200,
        title="Green Leaf Cafe | Organic Coffee in Oslo",
        meta_description="Organic coffee and pastries served fresh every day in downtown Oslo.",
        h1_count=1,
        word_count=400,
        meta_robots=None,
        x_robots_tag=None,
        is_indexable=True,
        internal_link_count=5,
        image_count=2,
        images_missing_alt=0,
        content_hash="abc123",
    )
    defaults.update(overrides)
    # canonical_url/redirect_chain default to self-referencing (the common,
    # healthy case) -- derived AFTER url is resolved above so a test that
    # only overrides `url` doesn't silently end up with a canonical/chain
    # still pointing at the OLD default url. Phase 1's canonical-grouping
    # fix in analyze_cross_page means a stale fixed default here would
    # wrongly group every test page into one canonical group regardless of
    # its own url -- see that test class's own comment for why this
    # matters.
    defaults.setdefault("canonical_url", defaults["url"])
    defaults.setdefault("redirect_chain", [defaults["url"]])
    return SimpleNamespace(**defaults)


# ---------------------------------------------------------------------------
# Titles
# ---------------------------------------------------------------------------

def test_missing_title_is_high_severity():
    findings = opa.analyze_page(_page(title=""))
    finding = next(f for f in findings if f.rule_code == "missing_title")
    assert finding.severity == "high"


def test_healthy_title_has_no_finding():
    findings = opa.analyze_page(_page(title="A reasonably sized title for this page"))
    assert not any(f.rule_code.startswith("title_") or f.rule_code == "missing_title" for f in findings)


def test_long_title_is_low_severity():
    findings = opa.analyze_page(_page(title="X" * 80))
    assert any(f.rule_code == "title_too_long" and f.severity == "low" for f in findings)


def test_short_title_is_low_severity():
    findings = opa.analyze_page(_page(title="Home"))
    assert any(f.rule_code == "title_too_short" and f.severity == "low" for f in findings)


# ---------------------------------------------------------------------------
# Meta descriptions
# ---------------------------------------------------------------------------

def test_missing_meta_description_is_medium_severity():
    findings = opa.analyze_page(_page(meta_description=""))
    finding = next(f for f in findings if f.rule_code == "missing_meta_description")
    assert finding.severity == "medium"


def test_long_meta_description_is_low_severity():
    findings = opa.analyze_page(_page(meta_description="X" * 200))
    assert any(f.rule_code == "meta_description_too_long" and f.severity == "low" for f in findings)


def test_short_meta_description_is_low_severity():
    findings = opa.analyze_page(_page(meta_description="Too short"))
    assert any(f.rule_code == "meta_description_too_short" and f.severity == "low" for f in findings)


# ---------------------------------------------------------------------------
# Headings
# ---------------------------------------------------------------------------

def test_missing_h1_is_high_severity():
    findings = opa.analyze_page(_page(h1_count=0))
    finding = next(f for f in findings if f.rule_code == "missing_h1")
    assert finding.severity == "high"


def test_multiple_h1_is_informational_not_an_error():
    """This agent's CLAUDE.md explicitly says not to always flag multiple
    H1s as wrong."""
    findings = opa.analyze_page(_page(h1_count=3))
    finding = next(f for f in findings if f.rule_code == "multiple_h1")
    assert finding.severity == "informational"


def test_single_h1_has_no_heading_finding():
    findings = opa.analyze_page(_page(h1_count=1))
    assert not any(f.rule_code in ("missing_h1", "multiple_h1") for f in findings)


# ---------------------------------------------------------------------------
# Thin content
# ---------------------------------------------------------------------------

def test_thin_content_is_medium_severity():
    findings = opa.analyze_page(_page(word_count=50))
    finding = next(f for f in findings if f.rule_code == "thin_content")
    assert finding.severity == "medium"


def test_sufficient_content_has_no_thin_content_finding():
    findings = opa.analyze_page(_page(word_count=500))
    assert not any(f.rule_code == "thin_content" for f in findings)


def test_broken_page_is_not_flagged_as_thin_content():
    """A 404 page has word_count=0 by construction (see seo_page_analyzer)
    -- that's not a content-quality problem, it's already covered by the
    technical analyzer's broken_page finding."""
    findings = opa.analyze_page(_page(http_status=404, word_count=0))
    assert not any(f.rule_code == "thin_content" for f in findings)


# ---------------------------------------------------------------------------
# Images
# ---------------------------------------------------------------------------

def test_images_missing_alt_is_low_severity():
    findings = opa.analyze_page(_page(image_count=5, images_missing_alt=2))
    finding = next(f for f in findings if f.rule_code == "images_missing_alt")
    assert finding.severity == "low"
    assert "2 of 5" in finding.issue


def test_no_missing_alt_has_no_finding():
    findings = opa.analyze_page(_page(image_count=5, images_missing_alt=0))
    assert not any(f.rule_code == "images_missing_alt" for f in findings)


# ---------------------------------------------------------------------------
# Cross-page: duplicates
# ---------------------------------------------------------------------------

def test_duplicate_titles_flagged_for_each_affected_page():
    pages = [
        _page(url="https://greenleaf.test/a", title="Same Title", content_hash="h1"),
        _page(url="https://greenleaf.test/b", title="Same Title", content_hash="h2"),
        _page(url="https://greenleaf.test/c", title="Different Title", content_hash="h3"),
    ]
    findings = opa.analyze_cross_page(pages)
    dup_title_findings = [f for f in findings if f.rule_code == "duplicate_title"]
    assert {f.affected_url for f in dup_title_findings} == {"https://greenleaf.test/a", "https://greenleaf.test/b"}
    assert all(f.severity == "high" for f in dup_title_findings)


def test_unique_titles_produce_no_duplicate_finding():
    pages = [
        _page(url="https://greenleaf.test/a", title="Title A", content_hash="h1"),
        _page(url="https://greenleaf.test/b", title="Title B", content_hash="h2"),
    ]
    findings = opa.analyze_cross_page(pages)
    assert not any(f.rule_code == "duplicate_title" for f in findings)


def test_duplicate_meta_descriptions_are_medium_severity():
    pages = [
        _page(url="https://greenleaf.test/a", title="A", meta_description="Same desc", content_hash="h1"),
        _page(url="https://greenleaf.test/b", title="B", meta_description="Same desc", content_hash="h2"),
    ]
    findings = opa.analyze_cross_page(pages)
    dup = [f for f in findings if f.rule_code == "duplicate_meta_description"]
    assert len(dup) == 2
    assert all(f.severity == "medium" for f in dup)


def test_duplicate_content_via_real_hash_is_high_severity():
    pages = [
        _page(url="https://greenleaf.test/a", title="A", content_hash="same-hash"),
        _page(url="https://greenleaf.test/b", title="B", content_hash="same-hash"),
    ]
    findings = opa.analyze_cross_page(pages)
    dup_content = [f for f in findings if f.rule_code == "duplicate_content"]
    assert {f.affected_url for f in dup_content} == {"https://greenleaf.test/a", "https://greenleaf.test/b"}
    assert all(f.severity == "high" for f in dup_content)


def test_pages_with_no_content_hash_are_never_flagged_as_duplicate():
    """A broken/non-HTML page has content_hash=None -- must never be
    lumped together with other None-hash pages as 'duplicate content'."""
    pages = [
        _page(url="https://greenleaf.test/a", content_hash=None, http_status=404),
        _page(url="https://greenleaf.test/b", content_hash=None, http_status=404),
    ]
    findings = opa.analyze_cross_page(pages)
    assert not any(f.rule_code == "duplicate_content" for f in findings)


def test_pages_that_canonicalize_to_the_same_target_are_not_flagged_as_duplicate():
    """Phase 1: a page whose <link rel="canonical"> already points at
    another page has explicitly told search engines which version to
    index -- matching title/content there is by design, not a bug."""
    pages = [
        _page(url="https://greenleaf.test/", title="Home", content_hash="h1", canonical_url="https://greenleaf.test/"),
        _page(url="https://greenleaf.test/?ref=twitter", title="Home", content_hash="h1", canonical_url="https://greenleaf.test/"),
    ]
    findings = opa.analyze_cross_page(pages)
    assert not any(f.rule_code in ("duplicate_title", "duplicate_content") for f in findings)


def test_canonical_grouping_uses_normalized_urls():
    """A canonical tag written as the bare domain still groups correctly
    against the trailing-slash form of the same page (Phase 1's URL
    normalizer, reused here)."""
    pages = [
        _page(url="https://greenleaf.test/a", title="Same", content_hash="h1", canonical_url="https://greenleaf.test/target"),
        _page(url="https://greenleaf.test/b", title="Same", content_hash="h1", canonical_url="https://greenleaf.test/target/"),
    ]
    findings = opa.analyze_cross_page(pages)
    assert not any(f.rule_code in ("duplicate_title", "duplicate_content") for f in findings)


def test_two_distinct_canonical_groups_with_matching_content_are_still_flagged():
    """The actual bug this whole feature protects against: two genuinely
    DIFFERENT pages (different, non-matching canonicals) that happen to
    share identical title/content are still a real problem worth flagging."""
    pages = [
        _page(url="https://greenleaf.test/a", title="Same Title", content_hash="h1", canonical_url="https://greenleaf.test/a"),
        _page(url="https://greenleaf.test/b", title="Same Title", content_hash="h1", canonical_url="https://greenleaf.test/b"),
    ]
    findings = opa.analyze_cross_page(pages)
    assert any(f.rule_code == "duplicate_title" for f in findings)
    assert any(f.rule_code == "duplicate_content" for f in findings)


def test_no_canonical_falls_back_to_the_pages_own_url_as_its_group():
    pages = [
        _page(url="https://greenleaf.test/a", title="Same", content_hash="h1", canonical_url=None),
        _page(url="https://greenleaf.test/b", title="Same", content_hash="h1", canonical_url=None),
    ]
    findings = opa.analyze_cross_page(pages)
    assert any(f.rule_code == "duplicate_title" for f in findings)


def test_analyze_combines_per_page_and_cross_page_findings():
    pages = [
        _page(url="https://greenleaf.test/a", title="Same", content_hash="h1"),
        _page(url="https://greenleaf.test/b", title="Same", h1_count=0, content_hash="h2"),
    ]
    findings = opa.analyze(pages)
    codes = {f.rule_code for f in findings}
    assert "duplicate_title" in codes
    assert "missing_h1" in codes
