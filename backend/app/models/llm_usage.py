import uuid
from datetime import datetime, timezone
from sqlalchemy import Column, Text, Integer, DateTime, ForeignKey
from sqlalchemy.dialects.postgresql import UUID
from ..core.database import Base


class LLMUsageLog(Base):
    """One row per LLM API call, for the platform-admin usage dashboard
    (see api/admin.py). Only the Groq provider records usage today -- see
    the last_usage capture in rag/providers/groq_provider.py."""

    __tablename__ = "llm_usage_logs"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    business_id = Column(UUID(as_uuid=True), ForeignKey("businesses.id"), nullable=False, index=True)
    provider = Column(Text, nullable=False)
    model = Column(Text, nullable=True)
    # "chat" (a visitor message answered via run_rag) or "translate" (the
    # one-off fallback-message translation in api/businesses.py).
    kind = Column(Text, nullable=False)
    prompt_tokens = Column(Integer, nullable=False, default=0)
    completion_tokens = Column(Integer, nullable=False, default=0)
    total_tokens = Column(Integer, nullable=False, default=0)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), index=True)
