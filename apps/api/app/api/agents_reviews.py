"""Review & Reputation Agent -- HTTP wrapper. See apps/agents/
review-reputation/CLAUDE.md for the full spec and app/services/
review_service.py for the actual logic -- this file only maps HTTP <->
that service, the same split app/api/agents_seo.py uses for app/services/
seo_service.py.
"""

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel
from sqlalchemy.orm import Session

from ..core.database import get_db
from ..core.dependencies import get_current_user, get_current_business
from ..core.limiter import limiter
from ..integrations.google_reviews_client import GoogleReviewsError
from ..models.business import Business
from ..models.user import User
from ..services import plan_service, review_service

router = APIRouter(prefix="/api/agents/reviews", tags=["review-reputation"])


class _ReviewOut(BaseModel):
    id: str
    platform: str
    external_review_id: str | None
    customer_name: str | None
    rating: int | None
    review_text: str
    review_language: str | None
    review_date: str | None
    sentiment: str | None
    sentiment_score: float | None
    topics: list[str]
    positive_points: list[str]
    negative_points: list[str]
    primary_issue: str | None
    priority: str
    requires_response: bool
    requires_human_review: bool
    escalation_reason: str | None
    ai_response: str | None
    response_tone: str | None
    response_status: str
    analyzed_at: str | None

    @classmethod
    def from_orm_review(cls, review) -> "_ReviewOut":
        return cls(
            id=str(review.id),
            platform=review.platform,
            external_review_id=review.external_review_id,
            customer_name=review.customer_name,
            rating=review.rating,
            review_text=review.review_text,
            review_language=review.review_language,
            review_date=review.review_date.isoformat() if review.review_date else None,
            sentiment=review.sentiment,
            sentiment_score=review.sentiment_score,
            topics=review.topics or [],
            positive_points=review.positive_points or [],
            negative_points=review.negative_points or [],
            primary_issue=review.primary_issue,
            priority=review.priority,
            requires_response=review.requires_response,
            requires_human_review=review.requires_human_review,
            escalation_reason=review.escalation_reason,
            ai_response=review.ai_response,
            response_tone=review.response_tone,
            response_status=review.response_status,
            analyzed_at=review.analyzed_at.isoformat() if review.analyzed_at else None,
        )


def _require_enabled(business: Business) -> None:
    plan_service.require_feature(business, "review_reputation_enabled")


@router.get("", response_model=list[_ReviewOut])
def list_reviews(
    priority: str | None = None,
    sentiment: str | None = None,
    response_status: str | None = None,
    requires_human_review: bool | None = None,
    current_user: User = Depends(get_current_user),
    business: Business = Depends(get_current_business),
    db: Session = Depends(get_db),
):
    _require_enabled(business)
    reviews = review_service.list_reviews(
        db, str(current_user.business_id), priority, sentiment, response_status, requires_human_review
    )
    return [_ReviewOut.from_orm_review(r) for r in reviews]


class _CreateReviewRequest(BaseModel):
    review_text: str
    rating: int | None = None
    customer_name: str | None = None


@router.post("", response_model=_ReviewOut)
def create_review(
    body: _CreateReviewRequest,
    current_user: User = Depends(get_current_user),
    business: Business = Depends(get_current_business),
    db: Session = Depends(get_db),
):
    """A review typed/pasted directly into the dashboard -- for a business
    that wants to log/analyze a review they received somewhere this app
    doesn't (yet) import from automatically."""
    _require_enabled(business)
    review = review_service.create_manual_review(
        db, str(current_user.business_id), body.review_text, rating=body.rating, customer_name=body.customer_name
    )
    return _ReviewOut.from_orm_review(review)


class _ImportRequest(BaseModel):
    platform: str


@router.post("/import", response_model=list[_ReviewOut])
async def import_reviews(
    body: _ImportRequest,
    current_user: User = Depends(get_current_user),
    business: Business = Depends(get_current_business),
    db: Session = Depends(get_db),
):
    _require_enabled(business)
    try:
        reviews = await review_service.import_reviews(db, str(current_user.business_id), body.platform)
    except NotImplementedError as exc:
        raise HTTPException(status_code=501, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except GoogleReviewsError as exc:
        # "google" is a real platform (unlike the still-unbuilt ones above)
        # but this business hasn't connected real Google credentials yet, or
        # the live API call itself failed -- see google_reviews_client.py's
        # own error messages for exactly which. 502, not 501: the platform
        # IS implemented, this specific call to it just didn't succeed.
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    return [_ReviewOut.from_orm_review(r) for r in reviews]


@router.post("/{review_id}/analyze", response_model=_ReviewOut)
async def analyze_review(
    review_id: str,
    force: bool = False,
    current_user: User = Depends(get_current_user),
    business: Business = Depends(get_current_business),
    db: Session = Depends(get_db),
):
    _require_enabled(business)
    try:
        review = await review_service.analyze_review(db, str(current_user.business_id), review_id, force=force)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return _ReviewOut.from_orm_review(review)


class _GenerateResponseRequest(BaseModel):
    tone: str | None = None


@router.post("/{review_id}/generate-response", response_model=_ReviewOut)
async def generate_response(
    review_id: str,
    body: _GenerateResponseRequest = _GenerateResponseRequest(),
    current_user: User = Depends(get_current_user),
    business: Business = Depends(get_current_business),
    db: Session = Depends(get_db),
):
    _require_enabled(business)
    try:
        review = await review_service.generate_response(
            db, str(current_user.business_id), review_id, tone_override=body.tone
        )
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return _ReviewOut.from_orm_review(review)


class _EditResponseRequest(BaseModel):
    response_text: str


@router.patch("/{review_id}/response", response_model=_ReviewOut)
def edit_response(
    review_id: str,
    body: _EditResponseRequest,
    current_user: User = Depends(get_current_user),
    business: Business = Depends(get_current_business),
    db: Session = Depends(get_db),
):
    _require_enabled(business)
    try:
        review = review_service.edit_response(db, str(current_user.business_id), review_id, body.response_text)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return _ReviewOut.from_orm_review(review)


@router.post("/{review_id}/approve", response_model=_ReviewOut)
def approve_response(
    review_id: str,
    current_user: User = Depends(get_current_user),
    business: Business = Depends(get_current_business),
    db: Session = Depends(get_db),
):
    _require_enabled(business)
    try:
        review = review_service.approve_response(db, str(current_user.business_id), review_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return _ReviewOut.from_orm_review(review)


@router.post("/{review_id}/reject", response_model=_ReviewOut)
def reject_response(
    review_id: str,
    current_user: User = Depends(get_current_user),
    business: Business = Depends(get_current_business),
    db: Session = Depends(get_db),
):
    _require_enabled(business)
    try:
        review = review_service.reject_response(db, str(current_user.business_id), review_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return _ReviewOut.from_orm_review(review)


class _InsightsOut(BaseModel):
    review_count: int
    average_rating: float | None
    sentiment_breakdown: dict
    top_positive_topics: list[dict]
    top_negative_topics: list[dict]
    reviews_requiring_attention: int
    insufficient_data: bool
    summary: str | None = None


@router.get("/insights", response_model=_InsightsOut)
async def get_insights(
    days: int | None = 30,
    include_summary: bool = True,
    current_user: User = Depends(get_current_user),
    business: Business = Depends(get_current_business),
    db: Session = Depends(get_db),
):
    _require_enabled(business)
    insights = review_service.get_insights(db, str(current_user.business_id), days)
    summary = None
    if include_summary and not insights.insufficient_data:
        summary = await review_service.generate_reputation_summary(db, str(current_user.business_id), days)
    return _InsightsOut(
        review_count=insights.review_count,
        average_rating=insights.average_rating,
        sentiment_breakdown=insights.sentiment_breakdown,
        top_positive_topics=insights.top_positive_topics,
        top_negative_topics=insights.top_negative_topics,
        reviews_requiring_attention=insights.reviews_requiring_attention,
        insufficient_data=insights.insufficient_data,
        summary=summary,
    )


class _TrendsOut(BaseModel):
    current_period_days: int
    current_negative_pct: float | None
    previous_negative_pct: float | None
    negative_trend: str | None
    recurring_negative_topics: list[dict]
    sudden_spike: bool
    insufficient_data: bool


@router.get("/trends", response_model=_TrendsOut)
def get_trends(
    period_days: int = 30,
    current_user: User = Depends(get_current_user),
    business: Business = Depends(get_current_business),
    db: Session = Depends(get_db),
):
    _require_enabled(business)
    trends = review_service.get_trends(db, str(current_user.business_id), period_days)
    return _TrendsOut(
        current_period_days=trends.current_period_days,
        current_negative_pct=trends.current_negative_pct,
        previous_negative_pct=trends.previous_negative_pct,
        negative_trend=trends.negative_trend,
        recurring_negative_topics=trends.recurring_negative_topics,
        sudden_spike=trends.sudden_spike,
        insufficient_data=trends.insufficient_data,
    )


class _ChatRequest(BaseModel):
    message: str


class _ChatResponse(BaseModel):
    reply: str


@router.post("/chat", response_model=_ChatResponse)
async def chat(
    body: _ChatRequest,
    current_user: User = Depends(get_current_user),
    business: Business = Depends(get_current_business),
    db: Session = Depends(get_db),
):
    """Conversational entry point (this agent's CLAUDE.md "Chat
    Interaction") -- 'Analyze this review: ...', 'Write a response to this
    review: ...', 'What are customers complaining about most?'."""
    _require_enabled(business)
    reply = await review_service.handle_chat_message(db, str(current_user.business_id), body.message)
    return _ChatResponse(reply=reply)


class _DemoRequest(BaseModel):
    review_text: str
    tone: str | None = None


class _DemoResponseOut(BaseModel):
    sentiment: str
    sentiment_score: float
    topics: list[str]
    positive_points: list[str]
    negative_points: list[str]
    primary_issue: str | None
    priority: str
    requires_human_review: bool
    escalation_reason: str | None
    response_text: str
    response_tone: str


@router.post("/demo", response_model=_DemoResponseOut)
@limiter.limit("10/minute")
async def demo(request: Request, body: _DemoRequest):
    """Public, unauthenticated, never persisted -- powers the
    /demo/review-reputation marketing page (website/). Every other route
    in this file requires a real logged-in business (this is a tenant's
    OWN back-office tool, not a customer-facing widget) -- this route
    exists specifically so a website VISITOR can see how the agent would
    analyze/respond to a review of THEIR OWN business, without needing an
    account first. Rate-limited for the same reason every other public,
    unauthenticated LLM-calling route in this app is (agents_booking.py's
    /request, agents_voice.py's /dev/*): a real Groq/OpenAI cost per call,
    reachable by anyone who finds the URL.
    """
    result = await review_service.run_public_demo(body.review_text, tone_override=body.tone)
    analysis = result.analysis
    return _DemoResponseOut(
        sentiment=analysis.sentiment,
        sentiment_score=analysis.sentiment_score,
        topics=analysis.topics,
        positive_points=analysis.positive_points,
        negative_points=analysis.negative_points,
        primary_issue=analysis.primary_issue,
        priority=analysis.priority,
        requires_human_review=analysis.requires_human_review,
        escalation_reason=analysis.escalation_reason,
        response_text=result.response_text,
        response_tone=result.response_tone,
    )
