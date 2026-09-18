"""Shared website-fetching layer -- SSRF guard, redirect validation, robots
parsing, sitemap discovery, link-crawl fallback. Originally built inside
document_service.py for "import my website into the knowledge base"
(Phase 24 security requirements: reject private/internal IPs, cap crawl
size, respect robots.txt, re-validate every redirect hop). Extracted here
in Stage 2 of apps/agents/seo-copywriter/CLAUDE.md so the SEO Audit &
Optimization agent's own crawler (app/services/seo_page_analyzer.py,
seo_audit_service.py) uses the exact same hardened fetch path instead of a
second implementation -- see that CLAUDE.md's Phase 18: the LLM never
decides facts a program can determine; this module is the deterministic
foundation everything else is built on.

document_service.py re-exports the names it used to define locally
(assert_public_url as _assert_public_url, discover_website_pages,
MAX_CRAWL_PAGES, ...) so its own call sites and existing tests are
unaffected by the move.
"""
import ipaddress
import socket
from typing import List, Optional
from urllib.parse import urljoin, urlparse
from urllib.robotparser import RobotFileParser
from xml.etree import ElementTree

import httpx
from fastapi import HTTPException

CRAWL_USER_AGENT = "MielikkixBot/1.0"
MAX_FETCH_BYTES = 5 * 1024 * 1024

# Hard operational ceiling on a single "discover this site's pages" call,
# independent of any plan/agent-specific page limit a caller applies on
# top (e.g. SeoWebsite.crawl_tier's own 25/100/500 -- see models/
# seo_website.py) -- this bounds the discovery step itself.
MAX_CRAWL_PAGES = 40

_NON_PAGE_EXTENSIONS = (
    ".pdf", ".jpg", ".jpeg", ".png", ".gif", ".svg", ".webp", ".ico",
    ".zip", ".mp4", ".mp3", ".css", ".js", ".xml", ".json", ".woff", ".woff2",
)


def assert_public_url(url: str) -> None:
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https"):
        raise HTTPException(status_code=400, detail="Only http/https URLs are supported")
    if not parsed.hostname:
        raise HTTPException(status_code=400, detail="Invalid URL")

    # Basic SSRF guard: resolve the hostname and reject anything that isn't
    # a genuine public address (localhost/internal services/cloud metadata
    # endpoints).
    try:
        resolved_ip = socket.gethostbyname(parsed.hostname)
    except socket.gaierror:
        raise HTTPException(status_code=400, detail="Could not resolve URL host")

    ip = ipaddress.ip_address(resolved_ip)
    if ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved or ip.is_multicast:
        raise HTTPException(status_code=400, detail="URLs pointing to private/internal addresses are not allowed")


def site_root(url: str) -> str:
    parsed = urlparse(url)
    return f"{parsed.scheme}://{parsed.netloc}"


async def fetch_robots_txt_text(base_url: str) -> Optional[str]:
    """Raw robots.txt content, or None if it doesn't exist/couldn't be
    fetched -- used both by get_robot_parser below (crawl-time filtering)
    and by the SEO Audit's technical analyzer (seo_technical_analyzer.py),
    which needs the actual text to report syntax/declared-sitemap findings
    that a RobotFileParser object doesn't expose."""
    robots_url = urljoin(base_url + "/", "robots.txt")
    try:
        async with httpx.AsyncClient(timeout=8) as client:
            resp = await client.get(robots_url, headers={"User-Agent": CRAWL_USER_AGENT})
    except httpx.HTTPError:
        return None
    if resp.status_code >= 400:
        return None
    return resp.text


async def get_robot_parser(base_url: str) -> RobotFileParser:
    parser = RobotFileParser()
    text = await fetch_robots_txt_text(base_url)
    parser.parse(text.splitlines() if text is not None else [])
    return parser


def looks_like_page(url: str) -> bool:
    path = urlparse(url).path.lower()
    if any(path.endswith(ext) for ext in _NON_PAGE_EXTENSIONS):
        return False
    return True


async def fetch_sitemap_xml(sitemap_url: str, _depth: int = 0) -> List[str]:
    """Fetches and parses one sitemap file at an already-complete URL --
    follows one level of <sitemapindex> nesting. Best-effort: returns []
    on any failure rather than raising, since a missing/broken sitemap
    just means falling back to a link crawl."""
    if _depth > 1:  # one level of sitemap-index nesting is enough
        return []
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.get(sitemap_url, headers={"User-Agent": CRAWL_USER_AGENT})
        if resp.status_code >= 400 or not resp.text.strip():
            return []
        root = ElementTree.fromstring(resp.content)
    except (httpx.HTTPError, ElementTree.ParseError):
        return []

    tag = root.tag.lower()
    if tag.endswith("sitemapindex"):
        nested = [el.text.strip() for el in root.iter() if el.tag.lower().endswith("loc") and el.text]
        urls: List[str] = []
        for nested_url in nested[:5]:  # bounded -- don't chase an unbounded index
            urls.extend(await fetch_sitemap_xml(nested_url, _depth + 1))
            if len(urls) >= MAX_CRAWL_PAGES:
                break
        return urls
    return [el.text.strip() for el in root.iter() if el.tag.lower().endswith("loc") and el.text]


async def discover_sitemap_urls(base_url: str) -> List[str]:
    """base_url is a site root (e.g. https://example.com) -- resolves it to
    /sitemap.xml once, then hands off to fetch_sitemap_xml for the actual
    fetch+parse(+nested-index-following)."""
    sitemap_url = urljoin(base_url + "/", "sitemap.xml")
    return await fetch_sitemap_xml(sitemap_url)


async def discover_by_crawling(base_url: str, max_pages: int = MAX_CRAWL_PAGES) -> List[str]:
    from bs4 import BeautifulSoup

    domain = urlparse(base_url).netloc
    seen = {base_url}
    queue = [(base_url, 0)]
    found: List[str] = []

    async with httpx.AsyncClient(timeout=10) as client:
        while queue and len(found) < max_pages:
            url, depth = queue.pop(0)
            try:
                assert_public_url(url)
                resp = await client.get(url, headers={"User-Agent": CRAWL_USER_AGENT})
            except (httpx.HTTPError, HTTPException):
                continue
            if resp.status_code >= 400 or "text/html" not in resp.headers.get("content-type", ""):
                continue
            found.append(url)
            if depth >= 2:
                continue
            soup = BeautifulSoup(resp.text, "html.parser")
            for a in soup.find_all("a", href=True):
                link = urljoin(url, a["href"]).split("#")[0]
                parsed = urlparse(link)
                if parsed.netloc != domain or link in seen or not looks_like_page(link):
                    continue
                seen.add(link)
                if len(seen) <= max_pages * 4:  # bound queue growth on link-heavy pages
                    queue.append((link, depth + 1))
    return found


async def discover_website_pages(url: str, max_pages: int = MAX_CRAWL_PAGES) -> List[str]:
    """Sitemap first, link-crawl fallback; filtered by robots.txt and capped
    at max_pages either way."""
    assert_public_url(url)
    base_url = site_root(url)

    candidates = await discover_sitemap_urls(base_url)
    if not candidates:
        candidates = await discover_by_crawling(base_url, max_pages=max_pages)

    robots = await get_robot_parser(base_url)
    seen = set()
    pages: List[str] = []
    for page_url in candidates:
        if page_url in seen or not looks_like_page(page_url):
            continue
        seen.add(page_url)
        if urlparse(page_url).netloc != urlparse(base_url).netloc:
            continue
        if not robots.can_fetch(CRAWL_USER_AGENT, page_url):
            continue
        pages.append(page_url)
        if len(pages) >= max_pages:
            break
    return pages


async def fetch_with_redirects(
    url: str, max_bytes: int = MAX_FETCH_BYTES, max_redirects: int = 5
) -> tuple[httpx.Response, List[str]]:
    """Follows redirects manually (never httpx's own follow_redirects),
    re-validating each hop with assert_public_url -- otherwise a public URL
    could 302 to a private/internal address or cloud metadata endpoint and
    have that response used anyway. Returns the final response and the
    full chain of URLs visited (including the original), for callers that
    want to record it (e.g. SeoCrawledPage.redirect_chain)."""
    chain = [url]
    current_url = url
    async with httpx.AsyncClient(timeout=15, follow_redirects=False) as client:
        for _ in range(max_redirects + 1):
            assert_public_url(current_url)
            try:
                resp = await client.get(current_url, headers={"User-Agent": CRAWL_USER_AGENT})
            except httpx.HTTPError:
                raise HTTPException(status_code=400, detail="Could not fetch that URL")
            if resp.is_redirect:
                location = resp.headers.get("location")
                if not location:
                    raise HTTPException(status_code=400, detail="Invalid redirect response")
                current_url = str(httpx.URL(current_url).join(location))
                chain.append(current_url)
                continue
            break
        else:
            raise HTTPException(status_code=400, detail="Too many redirects")

    if len(resp.content) > max_bytes:
        raise HTTPException(status_code=400, detail="Page is too large")

    return resp, chain
