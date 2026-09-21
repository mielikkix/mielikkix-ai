"""AnalyticsProvider -- abstraction around real per-page traffic data, so
the SEO Audit & Optimization agent's action-plan prioritization (Stage 12,
see apps/agents/seo-audit/CLAUDE.md's "Professional tier roadmap") isn't
tightly coupled to Google Analytics specifically. Same idiom every other
provider in this package uses: an ABC + a get_*_provider() factory (root
CLAUDE.md convention #6).

Returns an empty dict (never a fabricated number) when real data isn't
available -- OAuth client not configured, business hasn't connected
Google, hasn't picked a GA4 property, the API call failed, or a given URL
just has no sessions in the window queried. Callers must treat a URL
missing from the result as "Not measured", never 0, exactly this agent's
"no fake numbers" rule.
"""
import asyncio
from abc import ABC, abstractmethod
from typing import Optional
from urllib.parse import urlparse

import requests

from ..core.config import settings
from ..core.encryption import decrypt
from .google_oauth_client import REQUEST_TIMEOUT_SECONDS, GoogleTokenRefreshError, get_access_token

ANALYTICS_SCOPE = "https://www.googleapis.com/auth/analytics.readonly"


class AnalyticsProvider(ABC):
    @abstractmethod
    async def get_page_sessions(self, urls: list[str]) -> dict[str, int]:
        """Sessions over a trailing 28-day window, keyed by the exact URLs
        passed in -- a URL missing from the returned dict means "no data
        for this URL", never a fabricated 0."""


class GoogleAnalyticsProvider(AnalyticsProvider):
    """Google Analytics Data API (GA4) -- talks to the REST endpoint
    directly via `requests` rather than googleapiclient's default httplib2
    transport, same reasoning as google_calendar_client.py's own docstring
    (confirmed-live httplib2/IPv6 issue on this dev machine)."""

    _ENDPOINT_TMPL = "https://analyticsdata.googleapis.com/v1beta/{property}:runReport"

    def __init__(self, client_id: str, client_secret: str, refresh_token: str, property_id: str):
        self._client_id = client_id
        self._client_secret = client_secret
        self._refresh_token = refresh_token
        self._property_id = property_id  # e.g. "properties/123456789"

    async def get_page_sessions(self, urls: list[str]) -> dict[str, int]:
        return await asyncio.to_thread(self._get_page_sessions_sync, urls)

    def _get_page_sessions_sync(self, urls: list[str]) -> dict[str, int]:
        try:
            token = get_access_token(self._client_id, self._client_secret, self._refresh_token, [ANALYTICS_SCOPE])
        except GoogleTokenRefreshError:
            return {}

        try:
            resp = requests.post(
                self._ENDPOINT_TMPL.format(property=self._property_id),
                headers={"Authorization": f"Bearer {token}"},
                json={
                    "dateRanges": [{"startDate": "28daysAgo", "endDate": "today"}],
                    "dimensions": [{"name": "pagePath"}],
                    "metrics": [{"name": "sessions"}],
                    "limit": "100000",
                },
                timeout=REQUEST_TIMEOUT_SECONDS,
            )
            resp.raise_for_status()
            data = resp.json()
        except (requests.RequestException, ValueError):
            return {}

        sessions_by_path: dict[str, int] = {}
        for row in data.get("rows", []) or []:
            dims = row.get("dimensionValues") or []
            mets = row.get("metricValues") or []
            if not dims or not mets:
                continue
            path = dims[0].get("value")
            raw = mets[0].get("value")
            if path is None or raw is None:
                continue
            try:
                sessions_by_path[path] = int(raw)
            except (TypeError, ValueError):
                continue

        # GA4 reports by path (e.g. "/menu"), not a full URL -- match each
        # crawled URL by its own path so the result can be keyed the same
        # way seo_page_analyzer's own URLs already are.
        result: dict[str, int] = {}
        for url in urls:
            path = urlparse(url).path or "/"
            if path in sessions_by_path:
                result[url] = sessions_by_path[path]
        return result


def get_analytics_provider(db, business_id) -> Optional[AnalyticsProvider]:
    """None (never a fabricated number) when: the OAuth client isn't
    configured on this server, this business hasn't connected Google, or
    has connected but not yet picked which GA4 property to read from --
    all three are valid, common states, not errors."""
    if not (settings.google_analytics_oauth_client_id and settings.google_analytics_oauth_client_secret):
        return None

    from ..models.seo_google_connection import SeoGoogleConnection

    connection = db.query(SeoGoogleConnection).filter(SeoGoogleConnection.business_id == business_id).first()
    if connection is None or not connection.analytics_property_id:
        return None

    return GoogleAnalyticsProvider(
        client_id=settings.google_analytics_oauth_client_id,
        client_secret=settings.google_analytics_oauth_client_secret,
        refresh_token=decrypt(connection.refresh_token_encrypted),
        property_id=connection.analytics_property_id,
    )
