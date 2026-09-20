import uuid
from datetime import datetime, timezone
from sqlalchemy import Column, Text, DateTime, JSON, ForeignKey
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
from ..core.database import Base

# Page-count ceiling per audit run, by crawl_tier -- independent of plan
# limits (see apps/agents/seo-audit/CLAUDE.md, Phase 4): this bounds a
# single audit's own crawl, not how many websites a business can register.
CRAWL_TIER_PAGE_LIMITS = {"starter": 25, "standard": 100, "advanced": 500}


class SeoWebsite(Base):
    """A website a business has registered for SEO Audit & Optimization --
    deliberately NOT the same thing as BusinessWebsite (models/website.py),
    which just counts widget-embed domains against PlanLimits.max_websites.
    A business can audit websites it doesn't even embed the chat widget on
    (see apps/agents/seo-audit/CLAUDE.md's "What already exists that
    this reuses" section for why these two models stay separate)."""

    __tablename__ = "seo_websites"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    business_id = Column(UUID(as_uuid=True), ForeignKey("businesses.id"), nullable=False, index=True)
    url = Column(Text, nullable=False)
    name = Column(Text, nullable=True)
    target_country = Column(Text, nullable=True)
    target_language = Column(Text, nullable=True)
    primary_category = Column(Text, nullable=True)
    target_keywords = Column(JSON, nullable=True, default=list)
    crawl_tier = Column(Text, nullable=False, default="starter")  # "starter" | "standard" | "advanced"
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))

    business = relationship("Business")
