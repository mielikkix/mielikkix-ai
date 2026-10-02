import uuid
from datetime import datetime, timezone
from sqlalchemy import Column, Text, Integer, DateTime, ForeignKey
from sqlalchemy.dialects.postgresql import UUID
from ..core.database import Base


class LLMUsageLog(Base):
    """One row per LLM API call, for the platform-admin AI Usage page (see
    api/admin.py). Groq rows come from the Chat Widget's provider
    (rag/pipeline.py's log_llm_usage); Claude/OpenAI rows from every
    agent-core LLMClient call (core/llm_usage.py)."""

    __tablename__ = "llm_usage_logs"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    # NULL for calls with no logged-in business: the public demo pages
    # (Support Triage, Voice, Booking, Review demos).
    business_id = Column(UUID(as_uuid=True), ForeignKey("businesses.id"), nullable=True, index=True)
    provider = Column(Text, nullable=False)
    model = Column(Text, nullable=True)
    # What the call was for: "chat" / "translate" (Chat Widget, Groq), or the
    # agent's usage_tag ("support_triage", "booking", "voice", "seo_copywriter",
    # "seo_keywords", "seo_recommendations", "reviews").
    kind = Column(Text, nullable=False)
    prompt_tokens = Column(Integer, nullable=False, default=0)
    completion_tokens = Column(Integer, nullable=False, default=0)
    total_tokens = Column(Integer, nullable=False, default=0)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), index=True)
