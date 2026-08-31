"""
Thin wrapper around the Google Business Profile API v4 (mybusiness.googleapis.com)
for the Review & Reputation Agent -- see apps/agents/review-reputation/CLAUDE.md
"Integrations needed" for exactly what real access this requires before it can
be used for real (a verified Business Profile location, an OAuth client, AND
Google's own separate Business Profile API access request approved -- unlike
Calendar API, this one isn't self-serve just by enabling it in Cloud Console).

Follows the same shape as google_calendar_client.py on purpose (same
"synchronous Google client library, so run it in asyncio.to_thread rather
than block the event loop" reasoning, same "talk to the REST API directly
via `requests` instead of googleapiclient.discovery.build()'s httplib2
transport" fix for the dead-IPv6-route problem documented there) -- read
that module's docstring first if this is your first time in either of these
two integration modules; this one doesn't repeat that reasoning inline.

OAuth note: this module only ever REFRESHES an already-obtained refresh
token (settings.google_reviews_refresh_token) -- it never runs the
interactive "sign in with Google" consent flow itself. That's a separate,
one-time, human-in-the-browser step: scripts/connect_google_reviews.py.
"""

import asyncio
from datetime import datetime
from typing import Optional

import requests
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials

from ..core.config import settings
from .review_platforms.base import ExternalReview

# Google Business Profile API v4 has no narrower "reviews only" scope the
# way Calendar API has calendar.freebusy vs calendar.events -- business.manage
# is the one scope that covers reviews.list/get/reply (and everything else
# about the connected location besides). Must exactly match the scope
# requested when the refresh token was obtained (scripts/connect_google_reviews.py).
REVIEWS_SCOPES = ["https://www.googleapis.com/auth/business.manage"]

_API_BASE = "https://mybusiness.googleapis.com/v4"

# Same reasoning as google_calendar_client.py's own _REQUEST_TIMEOUT_SECONDS
# / _CALENDAR_CALL_TIMEOUT_SECONDS pair: requests' own timeout= bounds each
# individual HTTP call, the outer asyncio.wait_for in _bounded() below also
# catches an unbounded credentials.refresh() taking too long.
_REQUEST_TIMEOUT_SECONDS = 10
_CALL_TIMEOUT_SECONDS = 30


class GoogleReviewsError(Exception):
    """Raised when the Google Business Profile API returns an error, or
    this module's credentials aren't configured yet. Callers
    (review_platforms/google_platform.py) decide their own fallback -- same
    convention as GoogleCalendarError before it."""


def _build_credentials(client_id: str, client_secret: str, refresh_token: str) -> Credentials:
    if not (client_id and client_secret and refresh_token):
        raise GoogleReviewsError(
            "Google Reviews isn't connected yet -- run scripts/connect_google_reviews.py "
            "and set the GOOGLE_REVIEWS_* values it prints in your .env. Needs a verified "
            "Business Profile location AND Google's own separate Business Profile API access "
            "request approved first -- see apps/agents/review-reputation/CLAUDE.md "
            "'Integrations needed'."
        )
    # Same lazy-refresh behavior as google_calendar_client.py's own
    # _build_credentials -- no access token supplied, google-auth mints one
    # from the refresh token the first time credentials.refresh() runs.
    return Credentials(
        token=None,
        refresh_token=refresh_token,
        token_uri="https://oauth2.googleapis.com/token",
        client_id=client_id,
        client_secret=client_secret,
        scopes=REVIEWS_SCOPES,
    )


# Google's v4 API returns star ratings as this enum, not a number --
# STAR_RATING_UNSPECIFIED (a review with no rating, rare but allowed by the
# API) maps to None rather than 0, so this agent's own "rating: Optional[int]"
# stays honest about "no rating given" vs. "a genuine 0", same distinction
# ExternalReview.rating's own Optional[int] type already exists for.
_STAR_RATING_TO_INT = {"ONE": 1, "TWO": 2, "THREE": 3, "FOUR": 4, "FIVE": 5}


def _parse_review(raw: dict) -> ExternalReview:
    """Converts one Business Profile API review object into this agent's
    generic ExternalReview shape (review_platforms/base.py) -- keeps every
    platform-specific field name (reviewId, starRating, createTime, ...)
    contained to this one function."""
    review_date = None
    if raw.get("createTime"):
        # Google returns RFC3339 with a literal "Z" suffix; Python's
        # datetime.fromisoformat wants "+00:00" instead on versions before
        # 3.11 -- replace() handles both old and new Python with no extra
        # dependency, same fix google_calendar_client.py would need if it
        # ever parsed a Google timestamp back into a datetime itself.
        review_date = datetime.fromisoformat(raw["createTime"].replace("Z", "+00:00"))
    return ExternalReview(
        external_id=raw["reviewId"],
        platform="google",
        customer_name=raw.get("reviewer", {}).get("displayName"),
        rating=_STAR_RATING_TO_INT.get(raw.get("starRating")),
        text=raw.get("comment", ""),
        review_date=review_date,
    )


def _fetch_reviews_sync(
    client_id: str, client_secret: str, refresh_token: str, account_id: str, location_id: str
) -> list[dict]:
    """The actual (synchronous, blocking) reviews.list call, following every
    page -- Google returns at most 50 reviews per page (nextPageToken). See
    this module's docstring for why the async wrapper below runs this in
    asyncio.to_thread instead of calling it directly."""
    credentials = _build_credentials(client_id, client_secret, refresh_token)
    credentials.refresh(Request())

    all_reviews: list[dict] = []
    page_token: Optional[str] = None
    while True:
        try:
            http_response = requests.get(
                f"{_API_BASE}/accounts/{account_id}/locations/{location_id}/reviews",
                headers={"Authorization": f"Bearer {credentials.token}"},
                params={"pageToken": page_token} if page_token else None,
                timeout=_REQUEST_TIMEOUT_SECONDS,
            )
            http_response.raise_for_status()
        except requests.RequestException as exc:
            raise GoogleReviewsError(f"Google Reviews list failed: {exc}") from exc

        body = http_response.json()
        all_reviews.extend(body.get("reviews", []))
        page_token = body.get("nextPageToken")
        if not page_token:
            break

    return all_reviews


def _get_review_sync(
    client_id: str, client_secret: str, refresh_token: str, account_id: str, location_id: str, review_id: str
) -> Optional[dict]:
    """The actual (synchronous, blocking) single-review get call. See
    _fetch_reviews_sync's docstring above for why this runs in
    asyncio.to_thread rather than being called directly."""
    credentials = _build_credentials(client_id, client_secret, refresh_token)
    credentials.refresh(Request())

    try:
        http_response = requests.get(
            f"{_API_BASE}/accounts/{account_id}/locations/{location_id}/reviews/{review_id}",
            headers={"Authorization": f"Bearer {credentials.token}"},
            timeout=_REQUEST_TIMEOUT_SECONDS,
        )
        if http_response.status_code == 404:
            return None
        http_response.raise_for_status()
    except requests.RequestException as exc:
        raise GoogleReviewsError(f"Google Reviews get failed: {exc}") from exc

    return http_response.json()


def _publish_reply_sync(
    client_id: str,
    client_secret: str,
    refresh_token: str,
    account_id: str,
    location_id: str,
    review_id: str,
    reply_text: str,
) -> None:
    """PUT .../reviews/{id}/reply -- Google's API replaces any existing
    reply wholesale (there's no separate create-vs-update endpoint), which
    matches this agent's own data model (one ai_response per review, not a
    reply thread). See this agent's CLAUDE.md "Human approval" section for
    why the only caller of this (review_platforms/google_platform.py's
    publish_response) is never reached until response_status == "approved"."""
    credentials = _build_credentials(client_id, client_secret, refresh_token)
    credentials.refresh(Request())

    try:
        http_response = requests.put(
            f"{_API_BASE}/accounts/{account_id}/locations/{location_id}/reviews/{review_id}/reply",
            headers={"Authorization": f"Bearer {credentials.token}"},
            json={"comment": reply_text},
            timeout=_REQUEST_TIMEOUT_SECONDS,
        )
        http_response.raise_for_status()
    except requests.RequestException as exc:
        raise GoogleReviewsError(f"Google Reviews reply failed: {exc}") from exc


async def _bounded(func, *args):
    try:
        return await asyncio.wait_for(asyncio.to_thread(func, *args), timeout=_CALL_TIMEOUT_SECONDS)
    except TimeoutError as exc:
        raise GoogleReviewsError(
            f"Google Reviews didn't respond within {_CALL_TIMEOUT_SECONDS}s -- please try again."
        ) from exc


class GoogleReviewsClient:
    """Not itself a ReviewPlatform/ReviewResponsePublisher -- those ABC
    implementations live in review_platforms/google_platform.py, the same
    split calendar_provider.py (ABC) / google_calendar_client.py (actual API
    calls) already uses. This class is just the real Google API surface,
    kept separate so google_platform.py's GoogleReviewsPlatform can stay a
    thin adapter onto the generic ExternalReview/PublishResult shapes the
    rest of this agent (review_service.py) already expects.
    """

    def __init__(
        self,
        client_id: Optional[str] = None,
        client_secret: Optional[str] = None,
        refresh_token: Optional[str] = None,
        account_id: Optional[str] = None,
        location_id: Optional[str] = None,
    ):
        self.client_id = client_id or settings.google_reviews_client_id
        self.client_secret = client_secret or settings.google_reviews_client_secret
        self.refresh_token = refresh_token or settings.google_reviews_refresh_token
        self.account_id = account_id or settings.google_reviews_account_id
        self.location_id = location_id or settings.google_reviews_location_id

    async def fetch_reviews(self, since: Optional[datetime] = None) -> list[ExternalReview]:
        raw_reviews = await _bounded(
            _fetch_reviews_sync,
            self.client_id,
            self.client_secret,
            self.refresh_token,
            self.account_id,
            self.location_id,
        )
        reviews = [_parse_review(raw) for raw in raw_reviews]
        if since is None:
            return reviews
        return [r for r in reviews if r.review_date and r.review_date >= since]

    async def get_review(self, external_id: str) -> Optional[ExternalReview]:
        raw = await _bounded(
            _get_review_sync,
            self.client_id,
            self.client_secret,
            self.refresh_token,
            self.account_id,
            self.location_id,
            external_id,
        )
        return _parse_review(raw) if raw else None

    async def publish_reply(self, external_review_id: str, reply_text: str) -> None:
        await _bounded(
            _publish_reply_sync,
            self.client_id,
            self.client_secret,
            self.refresh_token,
            self.account_id,
            self.location_id,
            external_review_id,
            reply_text,
        )
