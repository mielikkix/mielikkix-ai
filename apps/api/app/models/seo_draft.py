import uuid
from datetime import datetime, timezone
from sqlalchemy import Column, Text, DateTime, ForeignKey
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
from ..core.database import Base


class SeoDraft(Base):
    """SEO Copywriter's output -- deliberately a separate table from
    Product, never written to Product directly on generation (see this
    agent's own CLAUDE.md: "generating in bulk across a whole catalog and
    silently overwriting live, customer-facing copy without review is the
    one failure mode this agent must never have"). A human approves or
    rejects each draft explicitly (see services/seo_service.py); only
    approving copies it onto the real Product row.

    business_id is carried here too, even though it's derivable via
    product_id -> Product.business_id, so a tenant-scoped list query
    doesn't need a join for the common case of "show me my drafts".
    """

    __tablename__ = "seo_drafts"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    business_id = Column(UUID(as_uuid=True), ForeignKey("businesses.id"), nullable=False, index=True)
    product_id = Column(UUID(as_uuid=True), ForeignKey("products.id"), nullable=False, index=True)
    draft_description = Column(Text, nullable=False)
    draft_seo_title = Column(Text, nullable=False)
    draft_meta_description = Column(Text, nullable=False)
    status = Column(Text, nullable=False, default="draft")  # "draft" | "approved" | "rejected"
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))

    product = relationship("Product")
