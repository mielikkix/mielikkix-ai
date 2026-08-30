"""Factory for ReviewPlatform, mirroring app/rag/providers/__init__.py's
get_llm_provider() and app/integrations/calendar_provider.py's
get_calendar_provider() -- same "ABC + factory" idiom, applied to review
platforms. See base.py's own module docstring for why only "mock" is a
real implementation today.
"""

from typing import Optional

from .base import ExternalReview, PublishResult, ReviewPlatform, ReviewResponsePublisher

# Every platform this agent is meant to eventually support (see this
# agent's CLAUDE.md and the product's own agents.astro tagline) -- listed
# here even though only "mock" resolves to a real implementation, so a
# caller (or the dashboard's "connect a platform" UI, once it exists) has
# one place to see the full intended roster rather than guessing from
# whichever names happen to raise NotImplementedError today.
PLATFORM_NAMES = ["mock", "google", "facebook", "tripadvisor", "yelp", "trustpilot"]

_REAL_PLATFORM_REQUIREMENTS = {
    "google": "Google Business Profile API access (OAuth + a verified Business Profile location)",
    "facebook": "a Facebook Page access token with pages_read_user_content permission",
    "tripadvisor": "TripAdvisor Content API access (partner application required)",
    "yelp": "Yelp Fusion API access (developer application required)",
    "trustpilot": "Trustpilot Business API access (partner application required)",
}


def get_review_platform(platform: str) -> Optional[ReviewPlatform]:
    """Returns None for a platform name this function doesn't recognize at
    all. Raises NotImplementedError (not a silent no-op, and not a fake
    response) for a real platform name that isn't connected yet -- this
    task's own instruction is explicit: "do not implement fake
    integrations... clearly mark future integrations." A caller (see
    review_service.import_reviews) turns that into an honest 501, the same
    "coming soon, not upgrade-to-unlock" distinction plan_service.
    require_feature already makes for NOT_YET_IMPLEMENTED_FEATURES.
    """
    if platform == "mock":
        from .mock_platform import MockReviewPlatform

        return MockReviewPlatform()
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
