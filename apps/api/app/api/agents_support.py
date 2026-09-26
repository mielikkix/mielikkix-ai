"""
Support Triage -- HTTP wrapper. See apps/agents/support-triage/CLAUDE.md for
the full phased plan and app/services/support_service.py for the actual
logic (Phases 1-3, 5) -- this file only maps HTTP <-> that service, the same
split app/api/agents_booking.py already uses for app/services/booking_service.py.

WHY THIS FILE LIVES IN apps/api, NOT apps/agents/support-triage: same
reason as app/api/agents_voice.py and app/api/agents_booking.py -- apps/api
is the "shared modular agent process" apps/agents/CLAUDE.md describes;
apps/agents/support-triage stays a CLAUDE.md + scaffold, not a second
running process.
"""

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from ..core.database import get_db
from ..services import support_service

from ..core.limiter import limiter
from ..schemas.chat import MAX_CHAT_MESSAGE_CHARS, MAX_ID_CHARS

router = APIRouter(prefix="/api/agents/support", tags=["support-triage"])


class _ChatMessageRequest(BaseModel):
    session_id: str = Field(min_length=1, max_length=MAX_ID_CHARS)
    message: str = Field(min_length=1, max_length=MAX_CHAT_MESSAGE_CHARS)
    customer_email: str | None = Field(default=None, max_length=254)


class _ChatMessageResponse(BaseModel):
    reply: str
    escalated: bool
    ticket_id: str
    suggest_booking_flow: bool = False


@router.post("/chat/message", response_model=_ChatMessageResponse)
@limiter.limit("10/minute")
async def chat_message(request: Request, body: _ChatMessageRequest, db: Session = Depends(get_db)):
    """CORS note: this route relies on the standard, origin-restricted
    CORSMiddleware (app/main.py), NOT PublicRouteCORSMiddleware (app/core/
    cors.py) -- that second one exists specifically for routes embedded on
    arbitrary THIRD-PARTY tenant websites (the product's own chat widget),
    which this is not. This widget only ever runs on website/ (Mielikkix's
    own marketing site), so it should stay locked to the origins in
    settings.cors_origins_list, same as every other non-public route.
    """
    result = await support_service.handle_chat_message(db, body.session_id, body.message, body.customer_email)
    return _ChatMessageResponse(
        reply=result.reply,
        escalated=result.escalated,
        ticket_id=result.ticket_id,
        suggest_booking_flow=result.suggest_booking_flow,
    )
