import uuid
from datetime import datetime, timezone
from sqlalchemy import Column, Text, DateTime, Float, ForeignKey
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
from ..core.database import Base


class Conversation(Base):
    __tablename__ = "conversations"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    business_id = Column(UUID(as_uuid=True), ForeignKey("businesses.id"), nullable=False, index=True)
    session_id = Column(Text, nullable=False, index=True)
    visitor_id = Column(Text, nullable=True)
    # "website_widget", or "dashboard_test" for the dashboard's "Test your
    # chatbot" panel -- test chats never count toward the plan, the stats or
    # the Conversations list (QA 2026-10-02, E4/E5).
    channel = Column(Text, default="website_widget")
    # "open" | "closed". The owner closes a conversation from the dashboard; the
    # visitor writing again in the same session reopens it (QA 2026-10-02, D10).
    status = Column(Text, default="open")
    # Language detected from the visitor's latest message (rag/language_detect.py).
    language = Column(Text, nullable=True)
    started_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    ended_at = Column(DateTime(timezone=True), nullable=True)

    business = relationship("Business", back_populates="conversations")
    # Ordered: QA 2026-10-02 (D2) saw replies listed under the wrong question --
    # without an order_by, Postgres returns a joinedload's rows in any order.
    messages = relationship(
        "Message", back_populates="conversation", cascade="all, delete-orphan", order_by="Message.created_at"
    )
    leads = relationship("Lead", back_populates="conversation")

    @property
    def preview(self) -> str | None:
        """The visitor's first message, shortened -- shown in the Conversations list."""
        first = next((m.content for m in self.messages if m.sender == "visitor"), None)
        if first is None:
            return None
        return first if len(first) <= 140 else first[:139].rstrip() + "…"

    @property
    def last_message_at(self):
        return self.messages[-1].created_at if self.messages else self.started_at


class Message(Base):
    __tablename__ = "messages"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    conversation_id = Column(UUID(as_uuid=True), ForeignKey("conversations.id"), nullable=False, index=True)
    sender = Column(Text, nullable=False)
    content = Column(Text, nullable=False)
    intent = Column(Text, nullable=True)
    confidence = Column(Float, nullable=True)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))

    conversation = relationship("Conversation", back_populates="messages")
