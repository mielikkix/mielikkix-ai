import uuid
from datetime import datetime, timezone
from sqlalchemy import Column, Text, DateTime, ForeignKey
from sqlalchemy.dialects.postgresql import UUID
from ..core.database import Base


class CalendarConnection(Base):
    """A business's own connected Google Calendar -- the real per-tenant
    counterpart to the single global settings.google_calendar_* config
    Phase 1-3 used. One row per business (unique business_id): a business
    either has no connection yet (agents_booking.py treats that as
    "booking not configured for this business", never falling back to
    Mielikkix's own demo calendar) or has exactly one.
    """

    __tablename__ = "calendar_connections"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    business_id = Column(
        UUID(as_uuid=True), ForeignKey("businesses.id"), nullable=False, unique=True, index=True
    )
    # Encrypted at rest via core/encryption.py -- unlike Business.api_key
    # (plaintext), this grants ongoing access to a business's real Google
    # Calendar, so it's never stored or logged as plaintext. Read with
    # core/encryption.decrypt() immediately before use, never persisted
    # decrypted anywhere.
    refresh_token_encrypted = Column(Text, nullable=False)
    calendar_id = Column(Text, nullable=False, default="primary")
    # Shown in the dashboard Settings page ("Connected as: ...") so the
    # business owner can confirm which Google account this is, without
    # needing to decrypt anything to check -- captured once from Google's
    # userinfo response during the OAuth callback, not re-fetched later.
    google_account_email = Column(Text, nullable=True)
    connected_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
