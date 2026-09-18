"""Technical SEO analyzer (Stage 3 of apps/agents/seo-copywriter/CLAUDE.md)
-- turns an audit's crawled data (SeoCrawledPage rows) plus a fresh
robots.txt/sitemap fetch into SeoFinding rows. Deterministic only, per that
CLAUDE.md's Phase 18 hard boundary: severity always comes from a fixed
rule below, never LLM opinion. A later stage (Stage 6, recommendation
engine) is what turns these into human-readable explanations/priority
narrative -- this module only produces the facts and a fixed severity.

Per this agent's CLAUDE.md's "no fake data" rule and its explicit
instruction not to assume a robots.txt Disallow rule is wrong: a `noindex`
page or a Disallow rule is reported at Informational/Low severity with an
explanation of what it affects, not flagged as an error outright. Only
genuine conflicts (a sitemap-submitted page blocked by robots.txt, the
whole site disallowed) get a high/critical severity.
"""
from typing import List, Optional
from urllib.robotparser import RobotFileParser

from .seo_finding_common import FindingDraft, health_score

__all__ = ["FindingDraft", "health_score", "analyze", "analyze_robots_txt", "analyze_sitemap", "analyze_page"]


def analyze_robots_txt(
    robots_txt: Optional[str], robots_parser: RobotFileParser, base_url: str
) -> List[FindingDraft]:
    findings: List[FindingDraft] = []

    if robots_txt is None:
        findings.append(FindingDraft(
            category="technical",
            rule_code="robots_missing",
            severity="low",
            issue="No robots.txt found",
            explanation="Without a robots.txt, search engines assume everything is crawlable by "
                        "default -- not an error, but you have no place to declare your sitemap or "
                        "block low-value paths (admin, search results, etc.).",
            recommended_fix="Add a robots.txt with at least a Sitemap: declaration.",
        ))
        return findings

    # Whole-site block: if the crawler's own user-agent (or a generic '*'
    # rule) can't fetch the site root at all, indexing is almost certainly
    # broken -- this is the one robots.txt case worth a Critical severity,
    # since accidentally shipping "Disallow: /" to production is a common,
    # high-impact mistake.
    if not robots_parser.can_fetch("*", base_url + "/"):
        findings.append(FindingDraft(
            category="technical",
            rule_code="robots_blocks_entire_site",
            severity="critical",
            issue="robots.txt blocks the entire site from crawling",
            affected_url=base_url,
            explanation="A 'Disallow: /' rule (or equivalent) for all user-agents means search "
                        "engines are told not to crawl any page on this site.",
            recommended_fix="Remove or narrow the Disallow rule blocking the site root, unless "
                            "this is intentional (e.g. a staging environment).",
            evidence={"robots_txt": robots_txt[:2000]},
        ))

    if "sitemap:" not in robots_txt.lower():
        findings.append(FindingDraft(
            category="technical",
            rule_code="robots_missing_sitemap_declaration",
            severity="low",
            issue="robots.txt doesn't declare a sitemap location",
            explanation="Search engines can still discover a sitemap submitted directly through "
                        "Search Console, but declaring it in robots.txt is a standard, low-effort "
                        "way to help every crawler find it.",
            recommended_fix="Add a 'Sitemap: <url>' line to robots.txt.",
        ))

    return findings


def analyze_sitemap(sitemap_urls: List[str], robots_parser: RobotFileParser) -> List[FindingDraft]:
    findings: List[FindingDraft] = []

    if not sitemap_urls:
        findings.append(FindingDraft(
            category="technical",
            rule_code="sitemap_missing",
            severity="low",
            issue="No XML sitemap found",
            explanation="A sitemap isn't required, but it's the standard way to tell search "
                        "engines every URL you want indexed, especially on larger sites.",
            recommended_fix="Add a sitemap.xml and reference it from robots.txt.",
        ))
        return findings

    # Genuine conflict: a URL the site is actively submitting for indexing
    # (via the sitemap) is simultaneously told "don't crawl me" by
    # robots.txt. Unlike a plain Disallow rule (which might be intentional
    # for that path), this specific combination is very likely a mistake.
    blocked = [url for url in sitemap_urls if not robots_parser.can_fetch("*", url)]
    for url in blocked:
        findings.append(FindingDraft(
            category="technical",
            rule_code="sitemap_url_blocked_by_robots",
            severity="high",
            issue="Sitemap includes a URL blocked by robots.txt",
            affected_url=url,
            explanation="This URL is listed in the sitemap (submitted for indexing) but "
                        "robots.txt disallows crawling it -- search engines are given "
                        "contradictory instructions.",
            recommended_fix="Either remove this URL from the sitemap, or allow it in robots.txt.",
        ))

    return findings


def analyze_page(page) -> List[FindingDraft]:
    """Per-SeoCrawledPage technical checks. `page` is a SeoCrawledPage row
    (duck-typed here so this stays testable against a plain object/stub
    without needing a DB)."""
    findings: List[FindingDraft] = []

    if page.http_status is not None and page.http_status >= 400:
        findings.append(FindingDraft(
            category="technical",
            rule_code="broken_page",
            severity="high",
            issue=f"Page returned HTTP {page.http_status}",
            affected_url=page.url,
            explanation="A discovered page that returns an error status wastes crawl budget and, "
                        "if linked internally or externally, sends visitors and search engines to "
                        "a dead end.",
            recommended_fix="Fix the page, or remove/update whatever links to it.",
            evidence={"http_status": page.http_status},
        ))

    if page.redirect_chain and len(page.redirect_chain) > 2:
        findings.append(FindingDraft(
            category="technical",
            rule_code="long_redirect_chain",
            severity="medium",
            issue=f"Page reaches its final destination through {len(page.redirect_chain) - 1} redirects",
            affected_url=page.url,
            explanation="Multiple redirect hops slow down crawling and page load, and can dilute "
                        "link equity passed between the original and final URL.",
            recommended_fix="Point the original link/URL directly at the final destination.",
            evidence={"redirect_chain": page.redirect_chain},
        ))

    if page.is_indexable is False:
        source = "meta robots tag" if page.meta_robots and "noindex" in page.meta_robots.lower() else "X-Robots-Tag header"
        findings.append(FindingDraft(
            category="technical",
            rule_code="page_excluded_from_indexing",
            severity="informational",
            issue=f"Page is excluded from search indexing via its {source}",
            affected_url=page.url,
            explanation="This may be intentional (e.g. an admin, thank-you, or duplicate page) -- "
                        "listed so you can confirm it's excluded on purpose, not by mistake.",
            evidence={"meta_robots": page.meta_robots, "x_robots_tag": page.x_robots_tag},
        ))

    if not page.canonical_url:
        findings.append(FindingDraft(
            category="technical",
            rule_code="missing_canonical",
            severity="low",
            issue="Page has no canonical URL",
            affected_url=page.url,
            explanation="A canonical tag tells search engines which URL is the authoritative "
                        "version when the same content could be reachable at more than one "
                        "address (with/without trailing slash, tracking parameters, etc.).",
            recommended_fix="Add a self-referencing <link rel=\"canonical\"> tag.",
        ))
    elif page.canonical_url != page.url:
        findings.append(FindingDraft(
            category="technical",
            rule_code="canonical_points_elsewhere",
            severity="informational",
            issue="Page's canonical URL points to a different address",
            affected_url=page.url,
            explanation="Often intentional (e.g. a filtered/paginated view canonicalizing to the "
                        "main page) -- listed so you can confirm it's deliberate.",
            evidence={"canonical_url": page.canonical_url},
        ))

    return findings


def analyze(pages: list, robots_txt: Optional[str], robots_parser: RobotFileParser,
            sitemap_urls: List[str], base_url: str) -> List[FindingDraft]:
    """Runs every technical check for one audit and returns the combined
    finding drafts -- seo_audit_service.run_audit persists these as
    SeoFinding rows and computes health_score() from the result."""
    findings: List[FindingDraft] = []
    findings.extend(analyze_robots_txt(robots_txt, robots_parser, base_url))
    findings.extend(analyze_sitemap(sitemap_urls, robots_parser))
    for page in pages:
        findings.extend(analyze_page(page))
    return findings
