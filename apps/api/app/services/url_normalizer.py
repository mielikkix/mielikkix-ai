"""Deterministic URL normalization for crawl-time deduplication.

Fixes the SEO Audit & Optimization agent's most user-visible bug:
https://example.com and https://example.com/ (or any of the other
equivalent forms below) being discovered and crawled as two separate
pages, producing false "duplicate title" / "duplicate meta description" /
"duplicate content" findings against a site's own homepage.

normalize_url() defines EQUIVALENCE for crawling/dedup purposes only -- it
is not a redirect resolver and does not verify that, say, the http and
https variants of a URL actually serve identical content. For a real
website they always do; this agent's crawler doesn't fetch both to
confirm, matching the same "treat as one" convention every mainstream SEO
tool (Screaming Frog, Ahrefs, Google Search Console) already applies by
default.

What gets normalized:
- scheme: http/https treated as equivalent, canonicalized to https
- host: lowercased, a leading "www." stripped
- port: dropped if it's the default for the (already-canonicalized) scheme
- path: trailing slash stripped (except the bare root, which normalizes to
  no path at all -- matches web_crawl.site_root()'s own bare
  scheme://host form), and a trailing index.html/index.htm/index.php
  filename stripped
- query: tracking parameters (utm_*, fbclid, gclid, msclkid, etc.) removed,
  remaining parameters sorted for stable comparison
- fragment: always dropped -- never sent to the server, never
  meaningfully distinguishes one crawled page from another
"""
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

_TRACKING_PARAM_PREFIXES = ("utm_",)
_TRACKING_PARAM_EXACT = {
    "fbclid", "gclid", "msclkid", "mc_cid", "mc_eid", "igshid", "yclid", "_ga", "_gl",
}
_INDEX_FILENAMES = ("index.html", "index.htm", "index.php")


def _is_tracking_param(key: str) -> bool:
    lowered = key.lower()
    return lowered.startswith(_TRACKING_PARAM_PREFIXES) or lowered in _TRACKING_PARAM_EXACT


def normalize_url(url: str) -> str:
    parts = urlsplit(url.strip())

    scheme = "https"  # http/https treated as equivalent for dedup

    host = (parts.hostname or "").lower()
    if host.startswith("www."):
        host = host[4:]
    # Ports are compared against the ORIGINAL scheme's default, not the
    # canonicalized one above -- an explicit ":443" on an http:// URL (or
    # ":80" on an https:// URL) is unusual but still means "the default
    # port for what this URL actually specified", not a real distinguishing
    # feature worth keeping.
    default_port = 443 if parts.scheme == "https" else 80
    if parts.port and parts.port != default_port:
        host = f"{host}:{parts.port}"

    path = parts.path or ""
    for name in _INDEX_FILENAMES:
        suffix = "/" + name
        if path.endswith(suffix):
            path = path[: -len(name)]  # keep the trailing slash left behind
            break
    if path == "/":
        path = ""
    elif path.endswith("/"):
        path = path.rstrip("/")

    query_pairs = sorted(
        (k, v) for k, v in parse_qsl(parts.query, keep_blank_values=True) if not _is_tracking_param(k)
    )
    query = urlencode(query_pairs)

    # Fragment always dropped (empty string in the 5-tuple below).
    return urlunsplit((scheme, host, path, query, ""))
