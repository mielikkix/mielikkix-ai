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

    finding_id is nullable and set only when a draft was generated FROM an
    SEO Audit finding (Stage 7 of this agent's CLAUDE.md -- integrating the
    Copywriter with audit findings) -- a draft generated from the original
    product-picker flow leaves it null exactly as before this column
    existed.

    product_id is nullable for the same reason: a finding's affected_url is
    a crawled page, which may or may not correspond to a Product row we
    actually own (Product has no `url` field to match against -- that
    mapping doesn't exist yet). When product_id is null, `url` carries the
    page this draft is actually for, and approving it can only ever mark it
    approved -- there is nothing in our own database to publish it onto,
    unlike the Product case where approval writes the live Product row.

    draft_type says which field(s) this draft actually populated -- a
    finding-driven draft only ever generates the one thing it was asked
    for (e.g. a `missing_title` finding only fills draft_seo_title), unlike
    the original bulk product flow ("full_copy") which always fills all
    three description/title/meta fields at once. draft_seo_title/
    draft_meta_description/draft_description are now all nullable because
    of this -- exactly one of them is populated depending on draft_type,
    except "full_copy" which populates all three as before.
    """

    __tablename__ = "seo_drafts"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    business_id = Column(UUID(as_uuid=True), ForeignKey("businesses.id"), nullable=False, index=True)
    product_id = Column(UUID(as_uuid=True), ForeignKey("products.id"), nullable=True, index=True)
    finding_id = Column(UUID(as_uuid=True), ForeignKey("seo_findings.id", ondelete="SET NULL"), nullable=True, index=True)
    url = Column(Text, nullable=True)
    # "full_copy" (original product-picker flow) | "title" | "meta_description" | "content"
    draft_type = Column(Text, nullable=False, default="full_copy")
    draft_description = Column(Text, nullable=True)
    draft_seo_title = Column(Text, nullable=True)
    draft_meta_description = Column(Text, nullable=True)
    status = Column(Text, nullable=False, default="draft")  # "draft" | "approved" | "rejected"
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))

    product = relationship("Product")
    finding = relationship("SeoFinding")
