import uuid
from datetime import datetime, timezone
from sqlalchemy import Column, Text, DateTime, Boolean, ForeignKey, Index
from sqlalchemy.dialects.postgresql import UUID
from ..core.database import Base


class ConsentRecord(Base):
    """Append-only log of what a user agreed to (or declined / withdrew) and
    when -- GDPR art. 7(1) requires being able to demonstrate consent. Never
    update a row to flip `granted`: a later decision is a NEW row, and the
    most recent row per (user_id, type) is the current state. `withdrawn_at`
    is set on the superseded granted row so the history reads naturally."""

    __tablename__ = "consent_records"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    # terms | dpa | age_confirmation | marketing_email (see core/legal.py)
    type = Column(Text, nullable=False)
    # Which version of the document was accepted; null for types with no document.
    document_version = Column(Text, nullable=True)
    granted = Column(Boolean, nullable=False)
    granted_at = Column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc))
    withdrawn_at = Column(DateTime(timezone=True), nullable=True)
    # register | settings | unsubscribe | reaccept
    source = Column(Text, nullable=False)
    # Keyed hash of the client IP (never the raw IP) -- enough to corroborate
    # a record if ever disputed, without storing the address itself.
    ip_hash = Column(Text, nullable=True)

    __table_args__ = (Index("ix_consent_records_user_type", "user_id", "type"),)
