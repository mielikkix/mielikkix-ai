"""Accessibility analyzer (Stage 14 of apps/agents/seo-audit/CLAUDE.md's
"Professional tier roadmap"). Deterministic only, same Phase 18 hard
boundary as every other analyzer here. Findings are category="on_page"
(folded into health_on_page, no new health_* column/migration needed --
this agent already tracks one accessibility-adjacent on-page check,
images_missing_alt, under the same category, so this extends existing
precedent rather than inventing a new bucket).

Every check here is static-HTML analysis only -- no headless-browser
rendering, matching this agent's existing crawl-time limitation (see
seo_page_analyzer.py). That rules out anything needing computed styles
(e.g. color-contrast checks), which is a real, honest gap, not something
to fake -- same "Not measured" rather than a guessed number rule Stage 8
(Core Web Vitals) already follows for missing data.
"""
from typing import List

from .seo_finding_common import FindingDraft, health_score

__all__ = ["FindingDraft", "health_score", "analyze", "analyze_page"]


def analyze_page(page) -> List[FindingDraft]:
    """Per-SeoCrawledPage accessibility checks. `page` is a SeoCrawledPage
    row (duck-typed, same convention as the other analyzers)."""
    findings: List[FindingDraft] = []

    # None means "couldn't assess" (a broken/non-HTML page has no <html>
    # element to check at all) -- only False is an actual finding.
    if getattr(page, "html_lang_present", None) is False:
        findings.append(FindingDraft(
            category="on_page",
            rule_code="missing_html_lang",
            severity="low",
            issue="Page's <html> tag has no lang attribute",
            affected_url=page.url,
            explanation="Without a lang attribute, screen readers can't reliably choose the "
                        "correct pronunciation/voice, and search engines lose a signal about "
                        "which language the page is written in.",
            recommended_fix="Add a lang attribute to the <html> tag, e.g. <html lang=\"en\">.",
        ))

    outline = getattr(page, "heading_outline", None) or []
    skips = [
        (prev, curr) for prev, curr in zip(outline, outline[1:])
        # Only skipping DEEPER matters (h2 -> h4) -- going back up (h3 -> h1,
        # starting a new section) is normal document structure, not a skip.
        if curr > prev + 1
    ]
    if skips:
        findings.append(FindingDraft(
            category="on_page",
            rule_code="heading_hierarchy_skip",
            severity="informational",
            issue=f"Page skips a heading level {len(skips)} time(s) (e.g. h{skips[0][0]} to h{skips[0][1]})",
            affected_url=page.url,
            explanation="Screen reader users often navigate by jumping between headings -- "
                        "skipping a level (e.g. an h2 followed directly by an h4) can make it "
                        "seem like content is missing, even though it renders fine visually.",
            recommended_fix="Restructure headings so each level follows the previous one without "
                            "skipping (h1 -> h2 -> h3), or use CSS instead of a heading tag purely "
                            "for visual sizing.",
            evidence={"heading_outline": outline},
        ))

    missing_label_count = getattr(page, "form_inputs_missing_label", 0) or 0
    if missing_label_count > 0:
        findings.append(FindingDraft(
            category="on_page",
            rule_code="form_inputs_missing_label",
            severity="medium",
            issue=f"{missing_label_count} form field(s) have no associated label",
            affected_url=page.url,
            explanation="A text input, textarea, or select with no <label> (or aria-label/"
                        "aria-labelledby) is unusable for a screen reader user -- they hear "
                        "\"edit text\" with no indication of what to type.",
            recommended_fix="Add a <label for=\"...\"> matching each field's id, or an "
                            "aria-label attribute directly on the field.",
            evidence={"form_inputs_missing_label": missing_label_count},
        ))

    missing_link_name_count = getattr(page, "links_missing_accessible_name", 0) or 0
    if missing_link_name_count > 0:
        findings.append(FindingDraft(
            category="on_page",
            rule_code="links_missing_accessible_name",
            severity="medium",
            issue=f"{missing_link_name_count} link(s) have no accessible name",
            affected_url=page.url,
            explanation="A link with no text, aria-label, title, or an image with alt text inside "
                        "it (often an icon-only button, e.g. a cart or menu icon) announces as "
                        "just \"link\" to a screen reader, with no indication of where it goes.",
            recommended_fix="Add visible text, an aria-label, or alt text on the image inside "
                            "each affected link.",
            evidence={"links_missing_accessible_name": missing_link_name_count},
        ))

    return findings


def analyze(pages: list) -> List[FindingDraft]:
    """Runs every accessibility check across a full audit's crawled pages."""
    findings: List[FindingDraft] = []
    for page in pages:
        findings.extend(analyze_page(page))
    return findings
