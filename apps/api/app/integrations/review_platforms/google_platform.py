"""
GoogleReviewsPlatform -- the real ReviewPlatform (+ ReviewResponsePublisher)
implementation for Google Business Profile. See
apps/agents/review-reputation/CLAUDE.md "Integrations needed" for exactly
what connecting this for real requires: a verified Business Profile
location, an OAuth client, AND Google's own separate Business Profile API
access request approved -- this isn't self-serve the way Calendar API is.

Thin adapter onto google_reviews_client.GoogleReviewsClient, same split as
calendar_provider.py (ABC) / google_calendar_client.py (actual API calls) --
this file has no HTTP/OAuth code of its own.

Until real Google access exists, this class still constructs fine -- it
only fails, with a clear GoogleReviewsError, the moment a real API call is
attempted (see google_reviews_client._build_credentials). That mirrors
GoogleCalendarProvider's own "lazy failure" behavior, and it's why
get_review_platform("google") (this package's __init__.py) can return a
real object today -- ready to use the moment real credentials are
configured -- instead of raising NotImplementedError the way the other
still-unbuilt platforms do.
"""

from datetime import datetime
from typing import Optional

from ..google_reviews_client import GoogleReviewsClient, GoogleReviewsError
from .base import ExternalReview, PublishResult, ReviewPlatform, ReviewResponsePublisher


class GoogleReviewsPlatform(ReviewPlatform, ReviewResponsePublisher):
    def __init__(self, client: Optional[GoogleReviewsClient] = None):
        # Accepts an already-built client (tests construct one with fake
        # credentials/a stubbed GoogleReviewsClient) -- defaults to reading
        # the global settings.google_reviews_* values, same "no-args means
        # Mielikkix's own configured connection" convention
        # GoogleCalendarProvider's own __init__ uses.
        self._client = client or GoogleReviewsClient()

    async def fetch_reviews(self, since: Optional[datetime] = None) -> list[ExternalReview]:
        return await self._client.fetch_reviews(since=since)

    async def get_review(self, external_id: str) -> Optional[ExternalReview]:
        return await self._client.get_review(external_id)

    async def publish_response(self, external_review_id: str, response_text: str) -> PublishResult:
        # Never called until review_service's own approval check has
        # already passed (response_status == "approved") -- see this
        # agent's CLAUDE.md "Human approval" section. Catches
        # GoogleReviewsError itself (rather than letting it propagate) so a
        # failed publish comes back as a normal PublishResult(status="error")
        # the caller can show the user, not an unhandled 500.
        try:
            await self._client.publish_reply(external_review_id, response_text)
        except GoogleReviewsError as exc:
            return PublishResult(status="error", error=str(exc))
        return PublishResult(status="published", platform_response_id=external_review_id)
