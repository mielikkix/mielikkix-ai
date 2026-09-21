"""Per-page structured extraction for the SEO Audit & Optimization agent's
crawler (Stage 2 of apps/agents/seo-audit/CLAUDE.md). Deterministic
only -- no LLM involvement, per that CLAUDE.md's Phase 18 hard boundary
("the LLM never decides facts a program can determine"). Built on
web_crawl.fetch_with_redirects, the same hardened fetch/SSRF/redirect-
validation path document ingestion uses -- not a second implementation.
"""
import hashlib
import json
import re
from dataclasses import dataclass, field
from typing import List, Optional
from urllib.parse import urljoin, urlparse

from . import web_crawl

# Form controls that need an accessible name -- matches axe-core's own
# "label"/"input-button-name" rule scope. <input type="hidden"> and button
# types (already covered by their own visible text) are deliberately
# excluded, same "don't flag what isn't actually a problem" rule the
# technical analyzer already follows for robots.txt/noindex.
_LABELABLE_INPUT_TYPES = {
    "text", "email", "password", "tel", "url", "number", "search", "date",
    "datetime-local", "month", "week", "time", "color",
}


@dataclass
class PageAnalysis:
    url: str
    http_status: Optional[int]
    title: Optional[str]
    meta_description: Optional[str]
    h1_count: int
    word_count: int
    canonical_url: Optional[str]
    meta_robots: Optional[str]
    x_robots_tag: Optional[str]
    is_indexable: bool
    redirect_chain: List[str]
    internal_link_count: int
    image_count: int
    images_missing_alt: int
    content_hash: Optional[str] = None
    # Stage 13/14 (structured data + accessibility) -- see seo_audit.py's
    # SeoCrawledPage for what each field means; extracted here since raw
    # HTML is only ever available at crawl time, never persisted itself.
    structured_data_types: List[str] = field(default_factory=list)
    structured_data_invalid_count: int = 0
    html_lang_present: Optional[bool] = None
    heading_outline: List[int] = field(default_factory=list)
    form_inputs_missing_label: int = 0
    links_missing_accessible_name: int = 0


def _is_indexable(meta_robots: Optional[str], x_robots_tag: Optional[str]) -> bool:
    combined = f"{meta_robots or ''} {x_robots_tag or ''}".lower()
    return "noindex" not in combined


def _extract_structured_data(soup) -> tuple[List[str], int]:
    """Reads every <script type="application/ld+json"> block. A block that
    isn't valid JSON is a real, reportable problem (structured_data_analyzer
    flags it) -- not silently skipped, since a malformed JSON-LD block is
    invisible to search engines even though it's present in the markup."""
    types: List[str] = []
    invalid_count = 0

    def collect_types(node) -> None:
        if isinstance(node, dict):
            raw_type = node.get("@type")
            if isinstance(raw_type, str):
                types.append(raw_type)
            elif isinstance(raw_type, list):
                types.extend(t for t in raw_type if isinstance(t, str))
            graph = node.get("@graph")
            if isinstance(graph, list):
                for item in graph:
                    collect_types(item)
        elif isinstance(node, list):
            for item in node:
                collect_types(item)

    for tag in soup.find_all("script", attrs={"type": "application/ld+json"}):
        raw = tag.string
        if raw is None or not raw.strip():
            continue
        try:
            collect_types(json.loads(raw))
        except (ValueError, TypeError):
            invalid_count += 1

    return types, invalid_count


def _extract_heading_outline(soup) -> List[int]:
    return [int(tag.name[1]) for tag in soup.find_all(re.compile(r"^h[1-6]$"))]


def _count_form_inputs_missing_label(soup) -> int:
    labeled_ids = {label["for"] for label in soup.find_all("label", attrs={"for": True})}
    missing = 0

    def has_label(tag) -> bool:
        if (tag.get("aria-label") or "").strip():
            return True
        if (tag.get("aria-labelledby") or "").strip():
            return True
        tag_id = tag.get("id")
        if tag_id and tag_id in labeled_ids:
            return True
        return tag.find_parent("label") is not None

    for tag in soup.find_all(["textarea", "select"]):
        if not has_label(tag):
            missing += 1

    for tag in soup.find_all("input"):
        input_type = (tag.get("type") or "text").strip().lower()
        if input_type not in _LABELABLE_INPUT_TYPES:
            continue
        if not has_label(tag):
            missing += 1

    return missing


def _count_links_missing_accessible_name(soup) -> int:
    missing = 0
    for a in soup.find_all("a", href=True):
        if a.get_text(strip=True):
            continue
        if (a.get("aria-label") or "").strip() or (a.get("aria-labelledby") or "").strip() or (a.get("title") or "").strip():
            continue
        if any((img.get("alt") or "").strip() for img in a.find_all("img")):
            continue
        missing += 1
    return missing


async def analyze_page(url: str) -> PageAnalysis:
    """Fetches one page and extracts deterministic SEO-relevant facts.
    Never raises for a genuinely-reachable-but-broken page (404, 500, a
    non-HTML response) -- those are recorded as data (http_status), the
    same "report, don't guess" principle this agent's CLAUDE.md insists on
    everywhere. Only raises for something the caller truly can't proceed
    from (SSRF-blocked target, unresolvable host, network failure, too
    many redirects) -- see web_crawl.fetch_with_redirects.
    """
    resp, chain = await web_crawl.fetch_with_redirects(url)
    x_robots_tag = resp.headers.get("x-robots-tag")

    if resp.status_code >= 400 or "text/html" not in resp.headers.get("content-type", ""):
        return PageAnalysis(
            url=url,
            http_status=resp.status_code,
            title=None,
            meta_description=None,
            h1_count=0,
            word_count=0,
            canonical_url=None,
            meta_robots=None,
            x_robots_tag=x_robots_tag,
            is_indexable=_is_indexable(None, x_robots_tag),
            redirect_chain=chain,
            internal_link_count=0,
            image_count=0,
            images_missing_alt=0,
        )

    from bs4 import BeautifulSoup

    soup = BeautifulSoup(resp.text, "html.parser")
    domain = urlparse(url).netloc

    # A separate copy with boilerplate stripped -- word_count/content_hash
    # should reflect the page's actual content, not nav/footer/header text
    # repeated identically on every page (which would make word_count
    # meaningless for a thin-content check and content_hash useless for
    # duplicate-content detection -- every page would "match").
    content_soup = BeautifulSoup(resp.text, "html.parser")
    for tag in content_soup(["script", "style", "nav", "footer", "header", "noscript"]):
        tag.decompose()
    visible_text = content_soup.get_text(separator=" ")
    word_count = len(visible_text.split())
    normalized = re.sub(r"\s+", " ", visible_text).strip().lower()
    content_hash = hashlib.sha256(normalized.encode("utf-8")).hexdigest() if normalized else None

    title_tag = soup.find("title")
    title = title_tag.get_text(strip=True) if title_tag else None

    meta_description = None
    meta_desc_tag = soup.find("meta", attrs={"name": "description"})
    if meta_desc_tag and meta_desc_tag.get("content"):
        meta_description = meta_desc_tag["content"].strip()

    meta_robots = None
    meta_robots_tag = soup.find("meta", attrs={"name": "robots"})
    if meta_robots_tag and meta_robots_tag.get("content"):
        meta_robots = meta_robots_tag["content"].strip()

    canonical_url = None
    canonical_tag = soup.find("link", attrs={"rel": "canonical"})
    if canonical_tag and canonical_tag.get("href"):
        canonical_url = urljoin(url, canonical_tag["href"].strip())

    h1_count = len(soup.find_all("h1"))

    internal_link_count = 0
    for a in soup.find_all("a", href=True):
        link = urljoin(url, a["href"])
        if urlparse(link).netloc == domain:
            internal_link_count += 1

    images = soup.find_all("img")
    image_count = len(images)
    # Phase 2 fix: alt="" (present, empty) is the correct, intentional HTML
    # for a decorative image -- it tells a screen reader to skip it, which
    # is different from the alt attribute being ABSENT entirely (a real
    # accessibility gap). `img.get("alt")` returns None only when the
    # attribute doesn't exist at all; treating alt="" the same as "missing"
    # produced false positives on any site using decorative images
    # correctly (confirmed live: mielikkix.ai's own flag icons and hero
    # decoration all use alt="" deliberately, and were being counted as
    # "missing alt text" before this fix).
    images_missing_alt = sum(1 for img in images if img.get("alt") is None)

    structured_data_types, structured_data_invalid_count = _extract_structured_data(soup)
    html_tag = soup.find("html")
    html_lang_present = bool(html_tag and (html_tag.get("lang") or "").strip())
    heading_outline = _extract_heading_outline(soup)
    form_inputs_missing_label = _count_form_inputs_missing_label(soup)
    links_missing_accessible_name = _count_links_missing_accessible_name(soup)

    return PageAnalysis(
        url=url,
        http_status=resp.status_code,
        title=title,
        meta_description=meta_description,
        h1_count=h1_count,
        word_count=word_count,
        canonical_url=canonical_url,
        meta_robots=meta_robots,
        x_robots_tag=x_robots_tag,
        is_indexable=_is_indexable(meta_robots, x_robots_tag),
        redirect_chain=chain,
        internal_link_count=internal_link_count,
        image_count=image_count,
        images_missing_alt=images_missing_alt,
        content_hash=content_hash,
        structured_data_types=structured_data_types,
        structured_data_invalid_count=structured_data_invalid_count,
        html_lang_present=html_lang_present,
        heading_outline=heading_outline,
        form_inputs_missing_label=form_inputs_missing_label,
        links_missing_accessible_name=links_missing_accessible_name,
    )
