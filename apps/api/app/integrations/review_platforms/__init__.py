"""Factory for ReviewPlatform, mirroring app/rag/providers/__init__.py's
get_llm_provider() and app/integrations/calendar_provider.py's
get_calendar_provider() -- same "ABC + factory" idiom, applied to review
platforms. See base.py's own module docstring for the mock, and
google_platform.py's own docstring for why "google" resolves to a real
(if not-yet-configured) implementation while the rest still raise
NotImplementedError.
"""

from typing import Optional

from sqlalchemy.orm import Session

from ...core.config import settings
from .base import ExternalReview, PublishResult, ReviewPlatform, ReviewResponsePublisher

# Every platform this agent is meant to eventually support (see this
# agent's CLAUDE.md and the product's own agents.astro tagline) -- listed
# here even though only "mock" and "google" resolve to a real
# implementation today, so a caller (or the dashboard's "connect a
# platform" UI, once it exists) has one place to see the full intended
# roster rather than guessing from whichever names happen to raise
# NotImplementedError today.
PLATFORM_NAMES = ["mock", "google", "facebook", "tripadvisor", "yelp", "trustpilot"]

_REAL_PLATFORM_REQUIREMENTS = {
    "facebook": "a Facebook Page access token with pages_read_user_content permission",
    "tripadvisor": "TripAdvisor Content API access (partner application required)",
    "yelp": "Yelp Fusion API access (developer application required)",
    "trustpilot": "Trustpilot Business API access (partner application required)",
}


def get_review_platform(
    platform: str, db: Optional[Session] = None, business_id: Optional[str] = None
) -> Optional[ReviewPlatform]:
    """Returns None for a platform name this function doesn't recognize at
    all. Raises NotImplementedError (not a silent no-op, and not a fake
    response) for a real platform name that isn't connected yet -- this
    task's own instruction is explicit: "do not implement fake
    integrations... clearly mark future integrations." A caller (see
    review_service.import_reviews) turns that into an honest 501, the same
    "coming soon, not upgrade-to-unlock" distinction plan_service.
    require_feature already makes for NOT_YET_IMPLEMENTED_FEATURES.

    "google" is the one exception: it always returns a real
    GoogleReviewsPlatform object (google_platform.py), even before real
    Google credentials are configured. Calling it before then fails with a
    clear GoogleReviewsError at the first actual API call, the same "lazy
    failure" GoogleCalendarProvider already uses -- see
    google_reviews_client.py's own docstring for exactly what's missing
    when that happens.

    `db`/`business_id` (both optional, same "no-args means the global demo/
    legacy config" convention calendar_provider.get_calendar_provider()
    uses): when both are given AND that business has a real
    ReviewConnection row (see review_oauth.py), "google" resolves to a
    GoogleReviewsPlatform built from THAT business's own decrypted
    credentials instead of the global settings.google_reviews_* values --
    the real per-tenant path. Falls back to the global config if either
    argument is omitted or the business has no connection yet, which is
    exactly what keeps the public demo (review_service.run_public_demo,
    no business at all) and any existing caller that only passes a bare
    platform name working unchanged.
    """
    if platform == "mock":
        from .mock_platform import MockReviewPlatform

        return MockReviewPlatform()
    if platform == "google":
        from .google_platform import GoogleReviewsPlatform

        if db is not None and business_id is not None:
            from ..google_reviews_client import GoogleReviewsClient
            from ...core.encryption import decrypt
            from ...models.review_connection import ReviewConnection

            connection = db.query(ReviewConnection).filter(ReviewConnection.business_id == business_id).first()
            # A connection that hasn't finished picking a location yet
            # (location_id still null -- see models/review_connection.py)
            # is treated the same as no connection at all: falls through to
            # the global settings.google_reviews_* below, which itself
            # fails fast with a clear "isn't connected yet" GoogleReviewsError
            # rather than silently querying the wrong location.
            if connection is not None and connection.location_id is not None:
                return GoogleReviewsPlatform(
                    GoogleReviewsClient(
                        refresh_token=decrypt(connection.refresh_token_encrypted),
                        account_id=connection.account_id,
                        location_id=connection.location_id,
                        # The per-tenant Web-application OAuth client (same
                        # one review_oauth.py's Flow uses), NOT the global
                        # Desktop-app settings.google_reviews_client_id/
                        # secret -- a refresh token can only be refreshed
                        # with the client_id/secret of whichever OAuth
                        # client actually issued it, same reasoning
                        # calendar_provider.py's own per-tenant branch
                        # documents.
                        client_id=settings.google_reviews_oauth_client_id,
                        client_secret=settings.google_reviews_oauth_client_secret,
                    )
                )
        return GoogleReviewsPlatform()
    if platform in _REAL_PLATFORM_REQUIREMENTS:
        raise NotImplementedError(
            f"{platform} isn't connected yet -- needs {_REAL_PLATFORM_REQUIREMENTS[platform]}. "
            "See apps/agents/review-reputation/CLAUDE.md's 'Integrations needed'."
        )
    return None


__all__ = [
    "ExternalReview",
    "PublishResult",
    "ReviewPlatform",
    "ReviewResponsePublisher",
    "PLATFORM_NAMES",
    "get_review_platform",
]
