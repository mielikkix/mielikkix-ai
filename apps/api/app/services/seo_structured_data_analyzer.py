"""Structured data analyzer (Stage 13 of apps/agents/seo-audit/CLAUDE.md's
"Professional tier roadmap"). Deterministic only, same Phase 18 hard
boundary as every other analyzer here -- severity always comes from a fixed
rule below, never LLM opinion. Findings are category="technical" (folded
into health_technical, no new health_* column/migration needed -- schema
markup validity is a crawlability/rich-snippet-eligibility concern, the
same bucket Screaming Frog itself puts it in).

Per this agent's "no fabricated findings" rule: a page simply having no
structured data at all is NOT flagged per-page (most pages on most sites
legitimately have none, and flagging every single one would be noise, not
signal, the same "don't assume it's wrong" principle the technical analyzer
already applies to robots.txt Disallow rules). Only two things are ever
flagged: a JSON-LD block that's present but fails to parse (a real, fixable
problem -- it's invisible to search engines despite being in the markup),
and the sitewide absence of ANY structured data across every crawled page
(one finding for the whole audit, not one per page).
"""
from typing import List

from .seo_finding_common import FindingDraft, health_score

__all__ = ["FindingDraft", "health_score", "analyze", "analyze_page"]


def analyze_page(page) -> List[FindingDraft]:
    """Per-SeoCrawledPage structured-data checks. `page` is a
    SeoCrawledPage row (duck-typed, same convention as the other
    analyzers, so this stays testable against a plain stub)."""
    findings: List[FindingDraft] = []

    invalid_count = getattr(page, "structured_data_invalid_count", 0) or 0
    if invalid_count > 0:
        findings.append(FindingDraft(
            category="technical",
            rule_code="structured_data_invalid_json",
            severity="medium",
            issue=f"Page has {invalid_count} structured data block(s) that aren't valid JSON",
            affected_url=page.url,
            explanation="A <script type=\"application/ld+json\"> block that isn't valid JSON is "
                        "invisible to search engines even though it's present in the page's "
                        "markup -- it can't be parsed, so none of the rich-snippet eligibility it "
                        "was meant to provide actually applies.",
            recommended_fix="Fix the JSON syntax in the structured data block (a trailing comma "
                            "or unquoted key are the most common causes) and re-run the audit.",
            evidence={"structured_data_invalid_count": invalid_count},
        ))

    return findings


def analyze(pages: list) -> List[FindingDraft]:
    """Runs every structured-data check across a full audit's crawled
    pages. Mirrors seo_technical_analyzer.analyze's shape (per-page checks
    plus one sitewide check) so seo_audit_service.run_audit can wire this
    in the same way."""
    findings: List[FindingDraft] = []
    for page in pages:
        findings.extend(analyze_page(page))

    has_any_structured_data = any(getattr(page, "structured_data_types", None) for page in pages)
    if pages and not has_any_structured_data:
        findings.append(FindingDraft(
            category="technical",
            rule_code="no_structured_data_sitewide",
            severity="low",
            issue="No structured data (JSON-LD) found on any crawled page",
            explanation="Structured data (e.g. Organization, WebSite, Product, or FAQPage schema) "
                        "helps search engines understand your content and can unlock rich results "
                        "(star ratings, sitelinks search box, FAQ accordions) in search listings. "
                        "Not having any isn't an error -- most pages work fine without it -- but "
                        "it's a missed opportunity most sites in your position would benefit from.",
            recommended_fix="Add Organization and WebSite JSON-LD to your homepage as a starting "
                            "point, then add more specific schema (Product, Article, FAQPage) to "
                            "pages where it applies.",
        ))

    return findings
