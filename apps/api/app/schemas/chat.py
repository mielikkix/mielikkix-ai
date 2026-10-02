from typing import Literal, Optional, List
from datetime import datetime
from uuid import UUID
from pydantic import BaseModel, Field

# Caps on public, unauthenticated input: every message goes to a paid LLM,
# so size is bounded here (rate limits only bound the number of requests).
MAX_CHAT_MESSAGE_CHARS = 2000
MAX_ID_CHARS = 100


class ChatMessageRequest(BaseModel):
    business_id: str = Field(max_length=MAX_ID_CHARS)
    session_id: str = Field(min_length=1, max_length=MAX_ID_CHARS)
    message: str = Field(min_length=1, max_length=MAX_CHAT_MESSAGE_CHARS)
    visitor_id: Optional[str] = Field(default=None, max_length=MAX_ID_CHARS)


class ChatMessageResponse(BaseModel):
    reply: str
    intent: Optional[str] = None
    confidence: Optional[float] = None
    session_id: str
    suggest_lead_capture: bool = False
    # True when _detect_intent (rag/pipeline.py) reads the message as a
    # booking request -- the widget renders an inline BookingFlow when this
    # is set, same "flag here, act on it in the widget" separation
    # suggest_lead_capture already uses. This app never calls Booking
    # Assistant's tools itself (see agents_booking.py) -- see "Mielikkix AI
    # -- Claude Code Project Instructions.md" Section 3: "chatbot should NOT
    # contain hardcoded booking logic."
    suggest_booking_flow: bool = False
    # The language chat_service detected from the visitor's own message (see
    # rag/language_detect.py) -- the widget uses this to keep its own UI
    # (lead form, placeholders) in sync with the conversation's language,
    # rather than a browser locale that has no relationship to what's typed.
    lang: str = "en"


class MessageOut(BaseModel):
    id: UUID
    sender: str
    content: str
    intent: Optional[str]
    created_at: datetime

    class Config:
        from_attributes = True


class ConversationOut(BaseModel):
    id: UUID
    session_id: str
    status: str
    started_at: datetime
    messages: List[MessageOut] = []
    channel: Optional[str] = None
    language: Optional[str] = None
    preview: Optional[str] = None
    last_message_at: Optional[datetime] = None


class ConversationStatusUpdate(BaseModel):
    status: Literal["open", "closed"]


class TestChatRequest(BaseModel):
    """The dashboard's "Test your chatbot" panel (QA 2026-10-02, E5)."""
    session_id: str = Field(min_length=1, max_length=MAX_ID_CHARS)
    message: str = Field(min_length=1, max_length=MAX_CHAT_MESSAGE_CHARS)

    class Config:
        from_attributes = True
