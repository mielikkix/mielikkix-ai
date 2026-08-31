import uuid
from datetime import datetime, timezone
from sqlalchemy import Column, Text, DateTime
from sqlalchemy.dialects.postgresql import UUID
from ..core.database import Base


class Booking(Base):
    __tablename__ = "bookings"

    # No business_id, same reasoning as app/models/ticket.py's Ticket: this
    # is Mielikkix's own demo/development booking calendar (see
    # app/api/agents_booking.py's module docstring, and "Mielikkix AI --
    # Claude Code Project Instructions.md" Section 5), not a per-tenant
    # resource yet -- there's no per-tenant Google Calendar OAuth connection
    # to attach one to (that's Phase 5). Real per-tenant bookings get a
    # business_id then, same as every other tenant-scoped table.
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    # Ties a booking back to the chat/widget session that created it, if any
    # (nullable -- a booking made straight from the standalone demo page has
    # no chat session behind it) -- same optional-linkage idea as Lead's
    # conversation_id, not a required relationship.
    session_id = Column(Text, nullable=True, index=True)
    name = Column(Text, nullable=False)
    email = Column(Text, nullable=False)
    phone = Column(Text, nullable=True)
    meeting_type = Column(Text, nullable=False, default="appointment")
    start_at = Column(DateTime(timezone=True), nullable=False)
    end_at = Column(DateTime(timezone=True), nullable=False)
    # The Google Calendar event this booking created -- lets a future
    # cancel/reschedule route (Phase 3+ of this agent's CLAUDE.md, not built
    # yet) look the event back up without re-searching by time.
    calendar_event_id = Column(Text, nullable=False)
    status = Column(Text, nullable=False, default="confirmed")  # "confirmed" | "cancelled"
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
