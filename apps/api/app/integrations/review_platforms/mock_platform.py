"""
MockReviewPlatform -- the one real ReviewPlatform implementation that
exists today. NOT a real integration: returns a small, clearly-fictional,
fixed set of reviews rather than calling any actual API. Exists so
review_service.import_reviews() and the dashboard's "Import reviews" flow
have something real to exercise locally/in demos before a real platform
(Google, Facebook, ...) is ever connected -- same role
scripts/setup_local_mielikkix_business.py's other seeded local data plays
elsewhere in this repo.

Every review here is invented for this purpose (clearly fictional business/
names, per this agent's own testing instructions -- never real customer
data). Deliberately includes the same spread of cases this agent's CLAUDE.md
testing section asks for: a clean 5-star, a 3-star mixed review, a 1-star
with an actual safety/misconduct allegation (to exercise escalation), a
repeated complaint (waiting time, appearing twice, to exercise trend
detection), and one non-English review (to exercise language matching).
"""

from datetime import datetime, timedelta, timezone
from typing import Optional

from .base import ExternalReview, ReviewPlatform

_NOW = datetime.now(timezone.utc)

MOCK_REVIEWS: list[ExternalReview] = [
    ExternalReview(
        external_id="mock-1",
        platform="mock",
        customer_name="Alex R.",
        rating=5,
        text="Absolutely fantastic experience from start to finish. The staff were "
        "incredibly friendly and the whole process was seamless. Highly recommend!",
        review_date=_NOW - timedelta(days=2),
    ),
    ExternalReview(
        external_id="mock-2",
        platform="mock",
        customer_name="Jamie T.",
        rating=4,
        text="Really good overall. Quick response times and the product quality was "
        "great. Only small thing is the price felt a little high for what it was.",
        review_date=_NOW - timedelta(days=4),
    ),
    ExternalReview(
        external_id="mock-3",
        platform="mock",
        customer_name="Morgan L.",
        rating=3,
        text="The food was excellent and the staff were very friendly, but we had to "
        "wait almost an hour for our order. Would come back but hoping it's faster "
        "next time.",
        review_date=_NOW - timedelta(days=6),
    ),
    ExternalReview(
        external_id="mock-4",
        platform="mock",
        customer_name="Sam K.",
        rating=2,
        text="Waited over 45 minutes past our booking time with no update from staff. "
        "Not the experience we were expecting based on other reviews.",
        review_date=_NOW - timedelta(days=9),
    ),
    ExternalReview(
        external_id="mock-5",
        platform="mock",
        customer_name="Riley P.",
        rating=1,
        text="We were seated and then completely ignored -- another long wait, over "
        "40 minutes this time, before anyone even acknowledged us. This keeps "
        "happening.",
        review_date=_NOW - timedelta(days=12),
    ),
    ExternalReview(
        external_id="mock-6",
        platform="mock",
        customer_name="Casey M.",
        rating=1,
        text="I want this on record: a staff member raised their voice at me and "
        "refused to let me speak to a manager. I felt genuinely unsafe and I am "
        "considering legal action.",
        review_date=_NOW - timedelta(days=1),
    ),
    ExternalReview(
        external_id="mock-7",
        platform="mock",
        customer_name="Elin S.",
        rating=5,
        text="Kjempebra opplevelse! Personalet var vennlige og hjelpsomme, og alt "
        "gikk raskt og smidig. Anbefales på det sterkeste.",
        review_date=_NOW - timedelta(days=15),
    ),
]


class MockReviewPlatform(ReviewPlatform):
    async def fetch_reviews(self, since: Optional[datetime] = None) -> list[ExternalReview]:
        if since is None:
            return list(MOCK_REVIEWS)
        return [r for r in MOCK_REVIEWS if r.review_date and r.review_date >= since]

    async def get_review(self, external_id: str) -> Optional[ExternalReview]:
        return next((r for r in MOCK_REVIEWS if r.external_id == external_id), None)
