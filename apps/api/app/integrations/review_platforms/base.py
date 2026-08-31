"""
ReviewPlatform -- abstraction around fetching reviews from an external
platform, so the Review & Reputation Agent (app/services/review_service.py)
isn't tightly coupled to any one review source. Same idiom this repo
already uses twice: app/rag/providers/ for swapping LLM providers, and
app/integrations/calendar_provider.py for swapping calendar providers (an
ABC + a get_*_provider() factory) -- applied here to review platforms.

Python note for a reader new to Python's abc module: `ABC` + `@abstractmethod`
is Python's version of a TypeScript `interface` -- a concrete provider below
must implement every abstractmethod here or Python refuses to instantiate
it, the same guarantee a TS `implements ReviewPlatform` gives you at
compile time, just enforced at class-definition time instead.

Google Business Profile is the one real (non-mock) platform implementation
that exists today -- google_platform.py's GoogleReviewsPlatform, still
unusable for a given deployment until real Google access is actually
configured (see that module's own docstring and
apps/agents/review-reputation/CLAUDE.md's "Integrations needed"). Facebook
Page reviews, Yelp, TripAdvisor, and Trustpilot are NOT connected --
this package's __init__.py's factory entry for each of those raises
NotImplementedError with an honest message (per root CLAUDE.md convention
#6 and this task's own instruction not to implement fake integrations)
rather than silently returning something that pretends to work.
MockReviewPlatform (mock_platform.py) exists purely for local dev/demo.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime
from typing import Optional


@dataclass
class ExternalReview:
    """One review as a platform's own API returns it -- generic across
    every platform (Google/Facebook/Yelp/... all expose roughly this same
    shape), so review_service.import_reviews() never needs to know which
    platform a given review actually came from beyond the `platform`
    string itself."""

    external_id: str
    platform: str
    customer_name: Optional[str]
    rating: Optional[int]
    text: str
    review_date: Optional[datetime]


@dataclass
class PublishResult:
    status: str  # "published" | "error"
    platform_response_id: Optional[str] = None
    error: Optional[str] = None


class ReviewPlatform(ABC):
    @abstractmethod
    async def fetch_reviews(self, since: Optional[datetime] = None) -> list[ExternalReview]:
        """All reviews available from this platform for the connected
        business, optionally only those posted after `since` (an
        incremental sync) -- see review_service.import_reviews()."""

    @abstractmethod
    async def get_review(self, external_id: str) -> Optional[ExternalReview]:
        """One specific review by the platform's own ID, or None if it
        doesn't exist / isn't visible to this connection anymore (e.g.
        deleted by the customer)."""


class ReviewResponsePublisher(ABC):
    """Separate from ReviewPlatform (not every platform that can be READ
    from can also be POSTED to with the credentials/scopes a given
    connection has) -- see this agent's CLAUDE.md "Human approval" section:
    nothing calls this automatically. A future "publish" action in the
    dashboard, only reachable after a human has approved a response
    (response_status == "approved"), would be the one caller."""

    @abstractmethod
    async def publish_response(self, external_review_id: str, response_text: str) -> PublishResult:
        """Posts response_text as this business's public reply to the
        review identified by external_review_id. Never called on a review
        whose response_status isn't "approved" -- that check is the
        caller's (review_service's) job, not this method's."""
