"""Per-page structured extraction for the SEO Audit & Optimization agent's
crawler (Stage 2 of apps/agents/seo-copywriter/CLAUDE.md). Deterministic
only -- no LLM involvement, per that CLAUDE.md's Phase 18 hard boundary
("the LLM never decides facts a program can determine"). Built on
web_crawl.fetch_with_redirects, the same hardened fetch/SSRF/redirect-
validation path document ingestion uses -- not a second implementation.
"""
import hashlib
import re
from dataclasses import dataclass
from typing import List, Optional
from urllib.parse import urljoin, urlparse

from . import web_crawl


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


def _is_indexable(meta_robots: Optional[str], x_robots_tag: Optional[str]) -> bool:
    combined = f"{meta_robots or ''} {x_robots_tag or ''}".lower()
    return "noindex" not in combined


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
    images_missing_alt = sum(1 for img in images if not (img.get("alt") or "").strip())

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
    )
