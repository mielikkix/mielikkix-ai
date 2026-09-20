import uuid
from datetime import datetime, timezone
from sqlalchemy import Column, Text, DateTime, ForeignKey, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from ..core.database import Base


class BusinessAgentAccess(Base):
    """Which Force agents (see apps/api/app/core/agent_catalog.py) a
    business has actually purchased -- deliberately independent of
    Business.plan (the chat-widget tier). Replaces the old
    PlanFeatures.booking_enabled/seo_copywriter_enabled/
    review_reputation_enabled/email_marketing_enabled booleans, which
    incorrectly bundled every agent into the Business/Growth chat-widget
    tiers for free; every agent is sold separately from the chat-widget
    plan, purchased on its own. See apps/agents/seo-audit/CLAUDE.md's
    "Standalone agent billing" decision.

    `status` is kept as history (never deleted) so a revoked agent leaves a
    record of when it was active, the same way SeoDraft keeps rejected
    drafts instead of deleting them.
    """

    __tablename__ = "business_agent_access"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    business_id = Column(UUID(as_uuid=True), ForeignKey("businesses.id"), nullable=False, index=True)
    agent_key = Column(Text, nullable=False)
    status = Column(Text, nullable=False, default="active")  # "active" | "revoked"
    activated_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))

    __table_args__ = (UniqueConstraint("business_id", "agent_key", name="uq_business_agent_access"),)
