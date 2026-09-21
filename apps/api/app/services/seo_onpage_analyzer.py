"""On-page SEO analyzer (Stage 4 of apps/agents/seo-audit/CLAUDE.md)
-- turns an audit's crawled data (SeoCrawledPage rows) into SeoFinding
rows for titles, meta descriptions, headings, thin content, duplicate
content, and image alt text. Deterministic only, same Phase 18 hard
boundary as seo_technical_analyzer.py: severity always comes from a fixed
rule below, never LLM opinion.

Per this agent's CLAUDE.md: multiple H1s are NOT automatically flagged as
wrong (informational only), and duplicate-content detection is based on a
real SHA-256 hash of each page's own extracted text (seo_page_analyzer.py)
-- never guessed from title/word-count alone.
"""
from collections import defaultdict
from typing import List

from .seo_finding_common import FindingDraft, health_score
from .url_normalizer import normalize_url

__all__ = ["FindingDraft", "health_score", "analyze", "analyze_page", "analyze_cross_page"]

# Conventional SEO length guidelines -- not hard requirements, hence Low/
# Medium rather than High/Critical severities throughout this file.
TITLE_MIN_LENGTH = 15
TITLE_MAX_LENGTH = 60
META_DESCRIPTION_MIN_LENGTH = 50
META_DESCRIPTION_MAX_LENGTH = 160
THIN_CONTENT_WORD_THRESHOLD = 300


def analyze_page(page) -> List[FindingDraft]:
    """Per-SeoCrawledPage on-page checks. `page` is duck-typed (a
    SeoCrawledPage row or any object with the same attributes), same
    pattern seo_technical_analyzer.analyze_page uses, so this stays
    testable without a DB."""
    findings: List[FindingDraft] = []

    title = (page.title or "").strip()
    if not title:
        findings.append(FindingDraft(
            category="on_page", rule_code="missing_title", severity="high",
            issue="Page has no title tag", affected_url=page.url,
            explanation="The title tag is one of the strongest on-page ranking signals and is "
                        "what shows as the clickable headline in search results.",
            recommended_fix="Add a unique, descriptive <title> tag.",
        ))
    elif len(title) > TITLE_MAX_LENGTH:
        findings.append(FindingDraft(
            category="on_page", rule_code="title_too_long", severity="low",
            issue=f"Title is {len(title)} characters, longer than the ~{TITLE_MAX_LENGTH} search "
                  f"engines typically display",
            affected_url=page.url,
            explanation="Search engines usually truncate longer titles in results.",
            recommended_fix="Shorten the title to the most important keywords/brand name.",
            evidence={"title": title, "length": len(title)},
        ))
    elif len(title) < TITLE_MIN_LENGTH:
        findings.append(FindingDraft(
            category="on_page", rule_code="title_too_short", severity="low",
            issue=f"Title is only {len(title)} characters",
            affected_url=page.url,
            explanation="A very short title may not be descriptive enough to earn clicks or "
                        "communicate what the page is about.",
            evidence={"title": title, "length": len(title)},
        ))

    meta_description = (page.meta_description or "").strip()
    if not meta_description:
        findings.append(FindingDraft(
            category="on_page", rule_code="missing_meta_description", severity="medium",
            issue="Page has no meta description", affected_url=page.url,
            explanation="Without one, search engines generate a snippet automatically from page "
                        "text, which is often less compelling than a written summary.",
            recommended_fix="Add a meta description that summarizes the page and invites a click.",
        ))
    elif len(meta_description) > META_DESCRIPTION_MAX_LENGTH:
        findings.append(FindingDraft(
            category="on_page", rule_code="meta_description_too_long", severity="low",
            issue=f"Meta description is {len(meta_description)} characters, longer than the "
                  f"~{META_DESCRIPTION_MAX_LENGTH} search engines typically display",
            affected_url=page.url,
            recommended_fix="Shorten the meta description.",
            evidence={"length": len(meta_description)},
        ))
    elif len(meta_description) < META_DESCRIPTION_MIN_LENGTH:
        findings.append(FindingDraft(
            category="on_page", rule_code="meta_description_too_short", severity="low",
            issue=f"Meta description is only {len(meta_description)} characters",
            affected_url=page.url,
            explanation="A very short description may not give searchers enough reason to click.",
            evidence={"length": len(meta_description)},
        ))

    if page.h1_count == 0:
        findings.append(FindingDraft(
            category="on_page", rule_code="missing_h1", severity="high",
            issue="Page has no H1 heading", affected_url=page.url,
            explanation="The H1 is the primary heading search engines and visitors use to "
                        "understand what the page is about.",
            recommended_fix="Add one H1 heading that describes the page's main topic.",
        ))
    elif page.h1_count > 1:
        # Deliberately Informational, not an error -- this agent's CLAUDE.md
        # explicitly warns against always flagging multiple H1s as wrong
        # (e.g. legitimate in HTML5 sectioning, or a component-based design).
        findings.append(FindingDraft(
            category="on_page", rule_code="multiple_h1", severity="informational",
            issue=f"Page has {page.h1_count} H1 headings", affected_url=page.url,
            explanation="Not necessarily an error -- HTML5 allows multiple H1s in sectioned "
                        "content -- but worth confirming the page still has one clear main topic.",
            evidence={"h1_count": page.h1_count},
        ))

    if page.http_status == 200 and page.word_count < THIN_CONTENT_WORD_THRESHOLD:
        findings.append(FindingDraft(
            category="on_page", rule_code="thin_content", severity="medium",
            issue=f"Page has only {page.word_count} words of visible content",
            affected_url=page.url,
            explanation="Pages with very little text often struggle to rank, though this can be "
                        "legitimate for a checkout, contact, or utility page -- use judgment.",
            recommended_fix="Expand the page with genuinely useful content, or note if this "
                            "page's short length is intentional.",
            evidence={"word_count": page.word_count},
        ))

    if page.images_missing_alt > 0:
        findings.append(FindingDraft(
            category="images", rule_code="images_missing_alt", severity="low",
            issue=f"{page.images_missing_alt} of {page.image_count} images have no alt text",
            affected_url=page.url,
            explanation="Alt text helps search engines and screen readers understand images. "
                        "Purely decorative images are fine without it -- this only flags the count "
                        "so you can review which ones actually need it.",
            recommended_fix="Add descriptive alt text to informational images.",
            evidence={"images_missing_alt": page.images_missing_alt, "image_count": page.image_count},
        ))

    return findings


def _canonical_group_key(page) -> str:
    """Pages that agree on a canonical target are the SAME logical page
    for duplicate-detection purposes -- a page whose <link rel="canonical">
    already points elsewhere has explicitly told search engines which
    version to index, so matching title/meta/content there is by design,
    not a bug to flag (Phase 1: "Never invent findings" applies here --
    flagging an intentionally-canonicalized page as a duplicate problem is
    exactly the kind of false positive that rule forbids). Normalized so
    "https://x.com/page" and "https://x.com/page/" resolve to one group
    even if the canonical tag itself wasn't written in normalized form."""
    target = (getattr(page, "canonical_url", None) or "").strip()
    return normalize_url(target) if target else normalize_url(page.url)


def analyze_cross_page(pages: list) -> List[FindingDraft]:
    """Checks that require comparing pages against each other within the
    same audit: duplicate titles, duplicate meta descriptions, and
    duplicate content (via each page's real content_hash). Pages sharing a
    canonical group (see _canonical_group_key) are collapsed to one
    representative before comparison, so two URLs that already declare
    themselves canonically equivalent are never flagged against each
    other -- only genuinely distinct pages that happen to match are."""
    findings: List[FindingDraft] = []

    seen_groups: set = set()
    representative_pages = []
    for page in pages:
        key = _canonical_group_key(page)
        if key in seen_groups:
            continue
        seen_groups.add(key)
        representative_pages.append(page)

    by_title = defaultdict(list)
    by_meta = defaultdict(list)
    by_content_hash = defaultdict(list)
    for page in representative_pages:
        if page.title and page.title.strip():
            by_title[page.title.strip()].append(page.url)
        if page.meta_description and page.meta_description.strip():
            by_meta[page.meta_description.strip()].append(page.url)
        if page.content_hash:
            by_content_hash[page.content_hash].append(page.url)

    for title, urls in by_title.items():
        if len(urls) < 2:
            continue
        for url in urls:
            findings.append(FindingDraft(
                category="on_page", rule_code="duplicate_title", severity="high",
                issue=f"Title is duplicated across {len(urls)} pages", affected_url=url,
                explanation="Identical titles make it harder for search engines to tell pages "
                            "apart and for searchers to know which result to click.",
                recommended_fix="Write a unique title for each page.",
                evidence={"title": title, "other_urls": [u for u in urls if u != url]},
            ))

    for meta, urls in by_meta.items():
        if len(urls) < 2:
            continue
        for url in urls:
            findings.append(FindingDraft(
                category="on_page", rule_code="duplicate_meta_description", severity="medium",
                issue=f"Meta description is duplicated across {len(urls)} pages", affected_url=url,
                recommended_fix="Write a unique meta description for each page.",
                evidence={"other_urls": [u for u in urls if u != url]},
            ))

    for content_hash, urls in by_content_hash.items():
        if len(urls) < 2:
            continue
        for url in urls:
            findings.append(FindingDraft(
                category="content", rule_code="duplicate_content", severity="high",
                issue=f"Page's visible content is identical to {len(urls) - 1} other page(s)",
                affected_url=url,
                explanation="Search engines may only index one of several pages with identical "
                            "content, and choose which one -- not necessarily the one you'd pick.",
                recommended_fix="Differentiate the content, or canonicalize to a single URL.",
                evidence={"other_urls": [u for u in urls if u != url]},
            ))

    return findings


def analyze(pages: list) -> List[FindingDraft]:
    """Runs every on-page check for one audit -- seo_audit_service.run_audit
    persists these as SeoFinding rows and computes health_score() from the
    result (stored as SeoAudit.health_on_page)."""
    findings: List[FindingDraft] = []
    for page in pages:
        findings.extend(analyze_page(page))
    findings.extend(analyze_cross_page(pages))
    return findings
