"""SearchConsoleProvider -- abstraction around real per-page search
performance data (impressions/clicks/average position), so the SEO Audit
& Optimization agent's action-plan prioritization (Stage 12, see
apps/agents/seo-audit/CLAUDE.md's "Professional tier roadmap") isn't
tightly coupled to Google Search Console specifically. Same idiom every
other provider in this package uses: an ABC + a get_*_provider() factory
(root CLAUDE.md convention #6).

Returns an empty dict (never a fabricated number) when real data isn't
available -- same set of reasons as analytics_provider.py's own docstring.
"""
import asyncio
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Optional

import requests

from ..core.config import settings
from ..core.encryption import decrypt
from .google_oauth_client import REQUEST_TIMEOUT_SECONDS, GoogleTokenRefreshError, get_access_token

SEARCH_CONSOLE_SCOPE = "https://www.googleapis.com/auth/webmasters.readonly"


@dataclass
class SearchConsoleMetrics:
    impressions: int
    clicks: int
    avg_position: float


class SearchConsoleProvider(ABC):
    @abstractmethod
    async def get_page_search_metrics(self, urls: list[str]) -> dict[str, SearchConsoleMetrics]:
        """Impressions/clicks/average position over a trailing 28-day
        window, keyed by the exact URLs passed in -- a URL missing from
        the returned dict means "no search data for this URL", never a
        fabricated zero/position."""


class GoogleSearchConsoleProvider(SearchConsoleProvider):
    """Google Search Console API v3 -- talks to the REST endpoint directly
    via `requests` rather than googleapiclient's default httplib2
    transport, same reasoning as google_calendar_client.py's own
    docstring (confirmed-live httplib2/IPv6 issue on this dev machine)."""

    _ENDPOINT_TMPL = "https://www.googleapis.com/webmasters/v3/sites/{site}/searchAnalytics/query"

    def __init__(self, client_id: str, client_secret: str, refresh_token: str, site_url: str):
        self._client_id = client_id
        self._client_secret = client_secret
        self._refresh_token = refresh_token
        self._site_url = site_url

    async def get_page_search_metrics(self, urls: list[str]) -> dict[str, SearchConsoleMetrics]:
        return await asyncio.to_thread(self._get_page_search_metrics_sync, urls)

    def _get_page_search_metrics_sync(self, urls: list[str]) -> dict[str, SearchConsoleMetrics]:
        try:
            token = get_access_token(self._client_id, self._client_secret, self._refresh_token, [SEARCH_CONSOLE_SCOPE])
        except GoogleTokenRefreshError:
            return {}

        from datetime import date, timedelta

        end = date.today()
        start = end - timedelta(days=28)

        try:
            resp = requests.post(
                self._ENDPOINT_TMPL.format(site=requests.utils.quote(self._site_url, safe="")),
                headers={"Authorization": f"Bearer {token}"},
                json={
                    "startDate": start.isoformat(),
                    "endDate": end.isoformat(),
                    "dimensions": ["page"],
                    "rowLimit": 25000,
                },
                timeout=REQUEST_TIMEOUT_SECONDS,
            )
            resp.raise_for_status()
            data = resp.json()
        except (requests.RequestException, ValueError):
            return {}

        metrics_by_url: dict[str, SearchConsoleMetrics] = {}
        for row in data.get("rows", []) or []:
            keys = row.get("keys") or []
            if not keys:
                continue
            page_url = keys[0]
            try:
                metrics_by_url[page_url] = SearchConsoleMetrics(
                    impressions=int(row.get("impressions", 0)),
                    clicks=int(row.get("clicks", 0)),
                    avg_position=round(float(row.get("position", 0.0)), 1),
                )
            except (TypeError, ValueError):
                continue

        # Search Console reports full page URLs (not just paths), so match
        # each crawled URL directly rather than by path.
        return {url: metrics_by_url[url] for url in urls if url in metrics_by_url}


def get_search_console_provider(db, business_id) -> Optional[SearchConsoleProvider]:
    """None (never a fabricated number) when: the OAuth client isn't
    configured on this server, this business hasn't connected Google, or
    has connected but not yet picked which verified site to read from --
    all three are valid, common states, not errors."""
    if not (settings.google_analytics_oauth_client_id and settings.google_analytics_oauth_client_secret):
        return None

    from ..models.seo_google_connection import SeoGoogleConnection

    connection = db.query(SeoGoogleConnection).filter(SeoGoogleConnection.business_id == business_id).first()
    if connection is None or not connection.search_console_site_url:
        return None

    return GoogleSearchConsoleProvider(
        client_id=settings.google_analytics_oauth_client_id,
        client_secret=settings.google_analytics_oauth_client_secret,
        refresh_token=decrypt(connection.refresh_token_encrypted),
        site_url=connection.search_console_site_url,
    )
