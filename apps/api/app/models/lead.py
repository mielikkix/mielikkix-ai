import uuid
from datetime import datetime, timezone
from sqlalchemy import Column, Text, DateTime, ForeignKey, Boolean
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
from ..core.database import Base


class Lead(Base):
    __tablename__ = "leads"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    business_id = Column(UUID(as_uuid=True), ForeignKey("businesses.id"), nullable=False, index=True)
    conversation_id = Column(UUID(as_uuid=True), ForeignKey("conversations.id"), nullable=True)
    name = Column(Text, nullable=False)
    email = Column(Text, nullable=True, index=True)
    phone = Column(Text, nullable=True)
    message = Column(Text, nullable=True)
    status = Column(Text, default="new")
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    # When this row last actually changed -- e.g. a repeat "Book a Free
    # Demo" submission from the same email (create_or_update_lead's own
    # dedup-by-email upsert) updates the EXISTING row rather than creating
    # a new one, and without this column that update was invisible: the
    # dashboard's Leads list sorts by created_at, so an updated old lead
    # never moved and looked untouched even seconds after a fresh
    # resubmission actually changed it. onupdate fires automatically on
    # any UPDATE (create_or_update_lead's re-assignment of every field
    # every call, the Mailchimp sync's own mailchimp_synced/contact_id
    # writeback, and PATCH /api/leads/{id}'s status change all bump this).
    updated_at = Column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    # Everything below is nullable and only ever populated by the marketing
    # site's "Book a Free Demo" form (website/src/pages/demo.astro), gated
    # server-side to settings.mailchimp_sync_business_id (see
    # app/services/lead_service.py) -- a generic tenant's own chat-widget
    # lead (apps/dashboard/src/widget/LeadForm.tsx) never sets these, same
    # as before this feature existed.
    first_name = Column(Text, nullable=True)
    last_name = Column(Text, nullable=True)
    company = Column(Text, nullable=True)
    # Free text (not an enum column) on purpose -- the frontend's <select>
    # options (see demo.astro) are the real constraint; a future option
    # added there needs no migration here, and an unrecognized/"Other"
    # value still stores fine, it just skips the tag mapping in
    # lead_service.py's _build_tags.
    industry = Column(Text, nullable=True)
    interest = Column(Text, nullable=True)
    # Where this lead came from -- defaults to "WEBSITE" in lead_service.py
    # for the marketing form; a generic chat-widget lead leaves this null,
    # same as it always has.
    source = Column(Text, nullable=True)
    marketing_consent = Column(Boolean, default=False, nullable=False)
    marketing_consent_at = Column(DateTime(timezone=True), nullable=True)
    mailchimp_synced = Column(Boolean, default=False, nullable=False)
    mailchimp_contact_id = Column(Text, nullable=True)
    mailchimp_last_synced_at = Column(DateTime(timezone=True), nullable=True)

    business = relationship("Business", back_populates="leads")
    conversation = relationship("Conversation", back_populates="leads")
