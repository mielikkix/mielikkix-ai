import uuid
from datetime import datetime, timezone
from sqlalchemy import Column, Text, DateTime, Float, ForeignKey
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
from ..core.database import Base


class Ticket(Base):
    __tablename__ = "tickets"

    # No business_id here, unlike every other tenant-scoped table in this
    # app (Business, Product, Lead, ...) -- Support Triage's chat widget
    # lives on website/ (Mielikkix's OWN marketing site) and talks to ITS
    # visitors, not a tenant's customers. The "tenant" for this one table is
    # the platform itself, see apps/agents/support-triage/CLAUDE.md.
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    # Ties a visitor's messages together into one Ticket without requiring
    # login (see this agent's CLAUDE.md, "Widget embed contract") -- the
    # widget generates one client-side per browser session and sends it on
    # every message.
    session_id = Column(Text, nullable=False, index=True)
    channel = Column(Text, nullable=False, default="web")  # "web" | "voice"
    status = Column(Text, nullable=False, default="open")  # "open" | "escalated" | "resolved"
    # category/priority/confidence are nullable and unset in Phase 0 (this
    # migration) -- Phase 1 fills these in once the LLM classification step
    # exists (see this agent's CLAUDE.md phased plan). A Phase 0 ticket
    # created by the bare echo route simply has none of these judgments yet.
    category = Column(Text, nullable=True)
    priority = Column(Text, nullable=True)  # "low" | "medium" | "high" | "urgent"
    confidence = Column(Float, nullable=True)
    customer_name = Column(Text, nullable=True)
    customer_email = Column(Text, nullable=True)
    customer_phone = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    updated_at = Column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    messages = relationship(
        "TicketMessage", back_populates="ticket", cascade="all, delete-orphan", order_by="TicketMessage.created_at"
    )


# Named TicketMessage, not Message -- app/models/conversation.py already
# defines a (different, tenant-scoped) Message class mapped to a "messages"
# table for the product's own tenant-facing chat widget. Two SQLAlchemy
# model classes can't share one table, and "Message" is already taken in
# this package's namespace (see app/models/__init__.py) -- this is a
# same-shape-but-different concept (a platform-level support ticket's
# thread, not a tenant's widget conversation), so it gets its own name and
# table rather than colliding with that one.
class TicketMessage(Base):
    __tablename__ = "ticket_messages"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    ticket_id = Column(UUID(as_uuid=True), ForeignKey("tickets.id"), nullable=False, index=True)
    role = Column(Text, nullable=False)  # "user" | "agent" | "human"
    content = Column(Text, nullable=False)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))

    ticket = relationship("Ticket", back_populates="messages")
