"""Tests for the Stage 3 technical SEO analyzer (app/services/
seo_technical_analyzer.py) -- pure functions, no DB/network. Every
assertion traces back to a specific input (robots.txt text, sitemap list,
or a fake crawled-page object), never an invented number.
"""
from types import SimpleNamespace
from urllib.robotparser import RobotFileParser

from app.services import seo_technical_analyzer as sta


def _robots(lines: list[str]) -> RobotFileParser:
    parser = RobotFileParser()
    parser.parse(lines)
    return parser


def _page(**overrides):
    defaults = dict(
        url="https://greenleaf.test/",
        http_status=200,
        title="Home",
        meta_description="desc",
        h1_count=1,
        word_count=200,
        canonical_url="https://greenleaf.test/",
        meta_robots=None,
        x_robots_tag=None,
        is_indexable=True,
        redirect_chain=["https://greenleaf.test/"],
        internal_link_count=5,
        image_count=2,
        images_missing_alt=0,
    )
    defaults.update(overrides)
    return SimpleNamespace(**defaults)


# ---------------------------------------------------------------------------
# robots.txt
# ---------------------------------------------------------------------------

def test_missing_robots_txt_is_low_severity_not_an_error():
    findings = sta.analyze_robots_txt(None, _robots([]), "https://greenleaf.test")
    assert len(findings) == 1
    assert findings[0].rule_code == "robots_missing"
    assert findings[0].severity == "low"


def test_robots_disallow_all_is_critical():
    text = "User-agent: *\nDisallow: /\n"
    findings = sta.analyze_robots_txt(text, _robots(text.splitlines()), "https://greenleaf.test")
    codes = {f.rule_code: f for f in findings}
    assert "robots_blocks_entire_site" in codes
    assert codes["robots_blocks_entire_site"].severity == "critical"


def test_robots_disallowing_one_path_is_not_flagged_as_blocking_everything():
    text = "User-agent: *\nDisallow: /admin\nSitemap: https://greenleaf.test/sitemap.xml\n"
    findings = sta.analyze_robots_txt(text, _robots(text.splitlines()), "https://greenleaf.test")
    assert not any(f.rule_code == "robots_blocks_entire_site" for f in findings)


def test_robots_missing_sitemap_declaration():
    text = "User-agent: *\nDisallow: /admin\n"
    findings = sta.analyze_robots_txt(text, _robots(text.splitlines()), "https://greenleaf.test")
    assert any(f.rule_code == "robots_missing_sitemap_declaration" and f.severity == "low" for f in findings)


def test_robots_with_sitemap_declared_has_no_missing_sitemap_finding():
    text = "User-agent: *\nSitemap: https://greenleaf.test/sitemap.xml\n"
    findings = sta.analyze_robots_txt(text, _robots(text.splitlines()), "https://greenleaf.test")
    assert not any(f.rule_code == "robots_missing_sitemap_declaration" for f in findings)


# ---------------------------------------------------------------------------
# sitemap
# ---------------------------------------------------------------------------

def test_no_sitemap_urls_reports_missing_sitemap():
    findings = sta.analyze_sitemap([], _robots([]))
    assert len(findings) == 1
    assert findings[0].rule_code == "sitemap_missing"
    assert findings[0].severity == "low"


def test_sitemap_url_blocked_by_robots_is_a_high_severity_conflict():
    robots = _robots(["User-agent: *", "Disallow: /secret"])
    findings = sta.analyze_sitemap(["https://greenleaf.test/secret", "https://greenleaf.test/public"], robots)
    assert len(findings) == 1
    assert findings[0].rule_code == "sitemap_url_blocked_by_robots"
    assert findings[0].severity == "high"
    assert findings[0].affected_url == "https://greenleaf.test/secret"


def test_sitemap_with_no_robots_conflict_reports_nothing():
    robots = _robots([])  # empty robots.txt allows everything
    findings = sta.analyze_sitemap(["https://greenleaf.test/"], robots)
    assert findings == []


# ---------------------------------------------------------------------------
# per-page checks
# ---------------------------------------------------------------------------

def test_broken_page_is_high_severity():
    findings = sta.analyze_page(_page(http_status=404))
    codes = {f.rule_code for f in findings}
    assert "broken_page" in codes
    assert next(f for f in findings if f.rule_code == "broken_page").severity == "high"


def test_healthy_page_has_no_broken_page_finding():
    findings = sta.analyze_page(_page(http_status=200))
    assert not any(f.rule_code == "broken_page" for f in findings)


def test_long_redirect_chain_is_medium_severity():
    chain = ["https://greenleaf.test/a", "https://greenleaf.test/b", "https://greenleaf.test/c", "https://greenleaf.test/d"]
    findings = sta.analyze_page(_page(redirect_chain=chain))
    assert any(f.rule_code == "long_redirect_chain" and f.severity == "medium" for f in findings)


def test_short_redirect_is_not_flagged():
    findings = sta.analyze_page(_page(redirect_chain=["https://greenleaf.test/a", "https://greenleaf.test/b"]))
    assert not any(f.rule_code == "long_redirect_chain" for f in findings)


def test_noindex_page_is_informational_not_an_error():
    findings = sta.analyze_page(_page(is_indexable=False, meta_robots="noindex"))
    finding = next(f for f in findings if f.rule_code == "page_excluded_from_indexing")
    assert finding.severity == "informational"
    assert "meta robots" in finding.issue


def test_noindex_via_header_is_attributed_to_the_header():
    findings = sta.analyze_page(_page(is_indexable=False, meta_robots=None, x_robots_tag="noindex"))
    finding = next(f for f in findings if f.rule_code == "page_excluded_from_indexing")
    assert "X-Robots-Tag" in finding.issue


def test_missing_canonical_is_low_severity():
    findings = sta.analyze_page(_page(canonical_url=None))
    assert any(f.rule_code == "missing_canonical" and f.severity == "low" for f in findings)


def test_self_referencing_canonical_has_no_finding():
    findings = sta.analyze_page(_page(url="https://greenleaf.test/", canonical_url="https://greenleaf.test/"))
    assert not any(f.rule_code in ("missing_canonical", "canonical_points_elsewhere") for f in findings)


def test_canonical_pointing_elsewhere_is_informational_not_an_error():
    findings = sta.analyze_page(_page(url="https://greenleaf.test/page?ref=1", canonical_url="https://greenleaf.test/page"))
    finding = next(f for f in findings if f.rule_code == "canonical_points_elsewhere")
    assert finding.severity == "informational"


# ---------------------------------------------------------------------------
# health score
# ---------------------------------------------------------------------------

def test_health_score_is_100_with_no_findings():
    assert sta.health_score([]) == 100


def test_health_score_deducts_by_severity():
    findings = [
        sta.FindingDraft(category="technical", rule_code="a", severity="critical", issue="x"),
        sta.FindingDraft(category="technical", rule_code="b", severity="low", issue="y"),
    ]
    assert sta.health_score(findings) == 100 - 20 - 2


def test_health_score_never_goes_below_zero():
    findings = [sta.FindingDraft(category="technical", rule_code=f"c{i}", severity="critical", issue="x") for i in range(10)]
    assert sta.health_score(findings) == 0


def test_informational_findings_do_not_affect_score():
    findings = [sta.FindingDraft(category="technical", rule_code="i", severity="informational", issue="x")]
    assert sta.health_score(findings) == 100


# ---------------------------------------------------------------------------
# analyze() -- full pipeline
# ---------------------------------------------------------------------------

def test_analyze_combines_robots_sitemap_and_page_findings():
    robots_text = "User-agent: *\nDisallow: /\n"
    robots = _robots(robots_text.splitlines())
    pages = [_page(http_status=404, url="https://greenleaf.test/gone")]

    findings = sta.analyze(pages, robots_text, robots, [], "https://greenleaf.test")

    codes = {f.rule_code for f in findings}
    assert "robots_blocks_entire_site" in codes
    assert "sitemap_missing" in codes
    assert "broken_page" in codes
