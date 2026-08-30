import uuid
from datetime import datetime, timezone
from sqlalchemy import Column, Text, DateTime, Integer, Float, Boolean, JSON, ForeignKey, Index
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
from ..core.database import Base


class Review(Base):
    """Review & Reputation Agent's core record -- one row per customer
    review, whether it arrived via a real platform integration (Google,
    Facebook, ...) or was pasted in manually / imported from the mock
    platform used for local dev and demos (see integrations/
    review_platforms/). See apps/agents/review-reputation/CLAUDE.md for
    the full architecture this supports.

    Tenant-scoped like every other business-owned table (Product, Lead,
    ...) -- business_id, not a platform-global table.
    """

    __tablename__ = "reviews"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    business_id = Column(UUID(as_uuid=True), ForeignKey("businesses.id"), nullable=False, index=True)

    # "google" | "facebook" | "tripadvisor" | "yelp" | "trustpilot" | "manual" | "chat"
    # -- "manual"/"chat" cover a review pasted directly (dashboard form /
    # the conversational endpoint) rather than imported from a platform.
    # See integrations/review_platforms/__init__.py's PLATFORM_NAMES.
    platform = Column(Text, nullable=False, default="manual")
    # The platform's own review ID -- present for anything actually
    # imported (never for "manual"/"chat"). Used for de-duplication on
    # import (see review_service.import_reviews): app-level check via a
    # query before insert, not a DB-level UNIQUE constraint -- same honest
    # tradeoff models/ticket.py's own session_id comment makes, since
    # "unique per platform" isn't something this column alone can express
    # as a simple UNIQUE (it's unique per business+platform+external_id).
    external_review_id = Column(Text, nullable=True, index=True)

    customer_name = Column(Text, nullable=True)
    # 1-5, nullable -- not every source guarantees a star rating (a plain
    # pasted review might have none), and this agent is deliberately told
    # not to infer sentiment FROM the rating alone anyway (see this
    # agent's CLAUDE.md: "a 5-star review can contain a complaint").
    rating = Column(Integer, nullable=True)
    review_text = Column(Text, nullable=False)
    # ISO 639-1 code the LLM detected the review is written in (e.g. "en",
    # "no") -- drives response-language matching (see review_service's
    # response generation prompt).
    review_language = Column(Text, nullable=True)
    # When the review was actually posted on the platform -- distinct from
    # created_at (when THIS ROW was imported/entered), which can lag well
    # behind it for a backfilled import.
    review_date = Column(DateTime(timezone=True), nullable=True)

    # --- Analysis (null until analyze_review() has run once -- see
    # review_service.py's own comment on why re-analysis isn't automatic) ---
    sentiment = Column(Text, nullable=True)  # "positive" | "neutral" | "negative" | "mixed"
    sentiment_score = Column(Float, nullable=True)  # -1.0 (very negative) .. 1.0 (very positive)
    # Flexible, not an enum column -- see this agent's CLAUDE.md on why the
    # category list is a prompt-level suggestion, not a hard-coded DB
    # constraint (new categories must be addable without a migration).
    topics = Column(JSON, nullable=True, default=list)
    positive_points = Column(JSON, nullable=True, default=list)
    negative_points = Column(JSON, nullable=True, default=list)
    primary_issue = Column(Text, nullable=True)
    priority = Column(Text, nullable=False, default="low")  # "low" | "medium" | "high" | "critical"
    requires_response = Column(Boolean, nullable=False, default=True)
    requires_human_review = Column(Boolean, nullable=False, default=False)
    # "legal_threat" | "safety_issue" | "serious_misconduct" | "discrimination"
    # | "fraud" | "high_reputation_risk" | "repeated_complaint" | "unknown" | null
    escalation_reason = Column(Text, nullable=True)
    analyzed_at = Column(DateTime(timezone=True), nullable=True)

    # --- Response (drafted, never auto-published -- see this agent's
    # CLAUDE.md "Human approval" section) ---
    ai_response = Column(Text, nullable=True)
    response_tone = Column(Text, nullable=True)
    # "none" | "draft" | "approved" | "rejected" | "published" -- "published"
    # is reserved for a future ReviewResponsePublisher integration (see
    # integrations/review_platforms/base.py); nothing sets it today.
    response_status = Column(Text, nullable=False, default="none")

    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    updated_at = Column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    business = relationship("Business")

    __table_args__ = (
        # The real dedup lookup review_service.import_reviews runs before
        # every insert -- an index, not a UNIQUE constraint (see
        # external_review_id's own comment on why).
        Index("ix_reviews_business_platform_external_id", "business_id", "platform", "external_review_id"),
    )
