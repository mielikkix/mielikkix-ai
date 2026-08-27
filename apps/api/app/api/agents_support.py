"""
Support Triage -- Phase 0 + Phase 1 (see apps/agents/support-triage/CLAUDE.md
for the full phased plan).

Phase 0 proved the ticket/message persistence and the widget's CORS setup
work end to end, with a bare echo reply. Phase 1 replaces that echo with a
real LLM classification + answering step -- "the LLM classifies the
message: category, priority, and confidence" and "high confidence ->
drafts and sends a reply itself" (this agent's CLAUDE.md, "Flow" steps 2-3).

Deliberately NOT in this phase (see that CLAUDE.md's phased plan):
- Escalation (Phase 2) -- a low-confidence/urgent classification is stored
  on the ticket, but nothing here emails a human or marks the ticket
  "escalated" yet. `escalated` in the response stays False for now.
- Booking Assistant handoff (Phase 3) -- a booking-shaped message
  ("I'd like to book a call") gets classified and answered like anything
  else this phase, not routed to Booking Assistant yet.

WHY THIS FILE LIVES IN apps/api, NOT apps/agents/support-triage: same
reason as app/api/agents_voice.py and app/api/agents_booking.py -- apps/api
is the "shared modular agent process" apps/agents/CLAUDE.md describes;
apps/agents/support-triage stays a CLAUDE.md + scaffold, not a second
running process.
"""

import json

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.orm import Session

from mielikkix_agent_core import LLMClient

from ..core.config import settings
from ..core.database import get_db
from ..models.ticket import Ticket, TicketMessage
from ..rag.embeddings import embed_query
from ..rag.pipeline import retrieve_chunks, retrieve_faqs, retrieve_products

router = APIRouter(prefix="/api/agents/support", tags=["support-triage"])

_llm_client = LLMClient()

# Python note: a triple-quoted string built with .format()-style {json braces
# escaped as {{ }} would get messy fast -- this is plain string
# concatenation instead, same readability tradeoff apps/api/app/api/
# agents_voice.py's _SYSTEM_PROMPT_BASE makes.
_CLASSIFICATION_SYSTEM_PROMPT_BASE = (
    "You are a support triage assistant for Mielikkix, an AI agent platform "
    "for small businesses. A visitor to Mielikkix's OWN website has sent a "
    "message via the chat widget -- classify it, and answer it yourself if "
    "you can do so confidently using the information provided below.\n\n"
    "Respond with ONLY a JSON object (no other text before or after it), in "
    "exactly this shape:\n"
    '{"category": "<short label, e.g. billing, pricing, technical, general>", '
    '"priority": "<low|medium|high|urgent>", '
    '"confidence": <number from 0.0 to 1.0 -- how confident you are that '
    '"answer" fully and correctly resolves the message>, '
    '"answer": "<a short, friendly reply to the visitor>"}\n\n'
    "priority guidance: \"urgent\" for anything suggesting the platform is "
    "broken/down, or a billing dispute; \"high\" for an account-blocking "
    "issue; \"medium\" for a real question that isn't urgent; \"low\" for "
    "general/casual messages.\n\n"
    "confidence guidance: if the information below doesn't actually answer "
    "the visitor's question, set confidence BELOW 0.3 and let \"answer\" say "
    "so honestly (e.g. offer to have someone follow up) rather than "
    "guessing or inventing details."
)


def _retrieve_context(db: Session, query: str) -> str:
    """Grounds classification/answering in settings.support_agent_business_id's
    actual FAQs/documents/products -- reuses the exact same retrieval
    functions agents_voice.py's _retrieve_context uses (rag/pipeline.py),
    rather than reimplementing embedding/scoring a second time. Returns ""
    if no business is configured at all, or nothing scores above noise
    level -- the system prompt above already instructs the LLM to answer
    honestly (low confidence) rather than guess when this is empty.
    """
    if not settings.support_agent_business_id:
        return ""

    query_embedding = embed_query(query)
    matches = (
        retrieve_chunks(db, settings.support_agent_business_id, query_embedding, top_k=4)
        + retrieve_faqs(db, settings.support_agent_business_id, query_embedding)
        + retrieve_products(db, settings.support_agent_business_id, query_embedding)
    )
    # Same sanity floor as agents_voice.py's _RAG_MINIMUM_SCORE -- not a
    # real relevance gate (see that module's long comment on why one
    # doesn't work well here), just enough to drop literal noise.
    return "\n\n".join(text for text, score in matches if score >= 0.05)


def _build_system_prompt(context: str) -> str:
    if context:
        return (
            f"{_CLASSIFICATION_SYSTEM_PROMPT_BASE}\n\nInformation about Mielikkix "
            f"to use when answering:\n\n{context}"
        )
    return (
        f"{_CLASSIFICATION_SYSTEM_PROMPT_BASE}\n\nNo specific Mielikkix "
        f"information is available for this message -- set confidence low "
        f"and be honest about that in your answer rather than guessing."
    )


class _Classification(BaseModel):
    category: str
    priority: str
    confidence: float
    answer: str


class _ClassificationError(Exception):
    """Raised when the LLM's JSON response doesn't parse into the shape
    _Classification expects -- caught by chat_message() so a malformed
    response degrades to a safe fallback reply instead of a 500."""


async def _classify(message: str, context: str) -> _Classification:
    result = await _llm_client.chat(
        [
            {"role": "system", "content": _build_system_prompt(context)},
            {"role": "user", "content": message},
        ],
        json_mode=True,
    )
    try:
        return _Classification(**json.loads(result.text))
    except (json.JSONDecodeError, TypeError, ValueError) as exc:
        raise _ClassificationError(f"Could not parse classification JSON: {result.text!r}") from exc


class _ChatMessageRequest(BaseModel):
    session_id: str
    message: str
    customer_email: str | None = None


class _ChatMessageResponse(BaseModel):
    reply: str
    escalated: bool
    ticket_id: str


def _get_or_create_ticket(db: Session, session_id: str, customer_email: str | None) -> Ticket:
    """One Ticket per session_id -- the widget generates one client-side
    per browser session and sends it on every message (see this agent's
    CLAUDE.md, "Widget embed contract"), so a visitor's whole conversation
    threads onto the same Ticket rather than creating a new one per
    message.

    Python note: `.first()`, not `.one()` -- `.one()` raises if it finds
    zero rows (we want to just create one instead) as well as if it finds
    more than one (which session_id being unique-per-session should
    prevent, but this isn't a DB-level UNIQUE constraint, so `.first()` is
    the honest choice here rather than a check this code doesn't actually
    enforce).
    """
    ticket = db.query(Ticket).filter(Ticket.session_id == session_id).first()
    if ticket is None:
        ticket = Ticket(session_id=session_id, customer_email=customer_email)
        db.add(ticket)
        db.flush()  # assigns ticket.id without needing a full commit yet
    return ticket


@router.post("/chat/message", response_model=_ChatMessageResponse)
async def chat_message(body: _ChatMessageRequest, db: Session = Depends(get_db)):
    """Phase 1: classifies the visitor's message (category/priority/
    confidence) and, when confident, answers it directly -- grounded in
    settings.support_agent_business_id's real FAQs/documents/products, the
    same RAG pipeline the Chat Widget and Voice Receptionist already use.

    `escalated` stays False this phase regardless of confidence/priority --
    deciding to actually escalate (email a human, mark the ticket
    "escalated") is Phase 2 (this agent's CLAUDE.md). This phase only
    records the classification on the ticket so Phase 2 has something to
    act on.

    CORS note: this route relies on the standard, origin-restricted
    CORSMiddleware (app/main.py), NOT PublicRouteCORSMiddleware (app/core/
    cors.py) -- that second one exists specifically for routes embedded on
    arbitrary THIRD-PARTY tenant websites (the product's own chat widget),
    which this is not. This widget only ever runs on website/ (Mielikkix's
    own marketing site), so it should stay locked to the origins in
    settings.cors_origins_list, same as every other non-public route.
    """
    ticket = _get_or_create_ticket(db, body.session_id, body.customer_email)

    db.add(TicketMessage(ticket_id=ticket.id, role="user", content=body.message))

    try:
        context = _retrieve_context(db, body.message)
        classification = await _classify(body.message, context)
        ticket.category = classification.category
        ticket.priority = classification.priority
        ticket.confidence = classification.confidence

        # Enforced here in code, not left to the LLM's own prompt-following
        # -- the system prompt already asks it to be honest at low
        # confidence, but trusting that alone means one off-instruction
        # response hands a visitor a hallucinated answer anyway. Below the
        # threshold, Phase 2 will additionally escalate to a human; Phase 1
        # just declines to guess (this agent's CLAUDE.md).
        if classification.confidence >= settings.support_agent_confidence_threshold:
            reply = classification.answer
        else:
            reply = "I'm not confident I can answer that correctly -- I'll have someone from our team follow up with you."
    except Exception:
        # Covers both _ClassificationError (malformed JSON back from the
        # LLM) and any other failure (network, rate limit, timeout) --
        # never leave the visitor without a reply if this step fails, same
        # "apologize, don't crash the conversation" convention as
        # agents_voice.py's _handle_turn.
        reply = "Sorry, I'm having trouble understanding right now. Could you try again in a moment, or a member of our team will follow up?"

    db.add(TicketMessage(ticket_id=ticket.id, role="agent", content=reply))
    db.commit()

    return _ChatMessageResponse(reply=reply, escalated=False, ticket_id=str(ticket.id))
