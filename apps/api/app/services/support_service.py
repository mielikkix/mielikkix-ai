"""Support Triage -- core logic, extracted from app/api/agents_support.py the
same way app/services/booking_service.py was extracted from agents_booking.py
(see that module's own docstring): so another agent (Voice Receptionist) can
call create_ticket() directly as a plain function, without one API router
importing another. See apps/agents/support-triage/CLAUDE.md for the full
phased plan this file implements (Phases 1-3, 5).

Python note for a reader coming from TS/Angular: `@dataclass` here plays the
same role a plain TS `interface`/class-with-no-methods does -- a typed bag of
fields, with `__init__`/`__eq__`/`__repr__` generated for you instead of
hand-written.
"""

import json
from dataclasses import dataclass

from sqlalchemy.orm import Session

from mielikkix_agent_core import LLMClient

from ..core.config import settings
from ..models.ticket import Ticket, TicketMessage
from ..notifications import notify_support_escalation
from ..rag.embeddings import embed_query
from ..rag.pipeline import retrieve_chunks, retrieve_faqs, retrieve_products, _detect_intent

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


@dataclass
class Classification:
    category: str
    priority: str
    confidence: float
    answer: str


class ClassificationError(Exception):
    """Raised when the LLM's JSON response doesn't parse into the shape
    Classification expects -- caught by handle_chat_message() so a malformed
    response degrades to a safe fallback reply instead of a 500."""


async def _classify(message: str, context: str) -> Classification:
    result = await _llm_client.chat(
        [
            {"role": "system", "content": _build_system_prompt(context)},
            {"role": "user", "content": message},
        ],
        json_mode=True,
    )
    try:
        return Classification(**json.loads(result.text))
    except (json.JSONDecodeError, TypeError, ValueError) as exc:
        raise ClassificationError(f"Could not parse classification JSON: {result.text!r}") from exc


def _get_or_create_ticket(
    db: Session, session_id: str, customer_email: str | None, channel: str = "web"
) -> Ticket:
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
        ticket = Ticket(session_id=session_id, customer_email=customer_email, channel=channel)
        db.add(ticket)
        db.flush()  # assigns ticket.id without needing a full commit yet
    return ticket


@dataclass
class ChatMessageResult:
    reply: str
    escalated: bool
    ticket_id: str
    # Phase 3: tells the widget to mount its own booking flow (the same
    # /api/agents/booking/request + /confirm two-step contract the tenant
    # chat widget's BookingFlow.tsx already uses -- see this agent's
    # CLAUDE.md "Booking Assistant handoff") instead of rendering `reply` as
    # a normal chat bubble waiting for a typed response.
    suggest_booking_flow: bool = False


async def handle_chat_message(
    db: Session, session_id: str, message: str, customer_email: str | None
) -> ChatMessageResult:
    """Phase 1 (classify + confidently answer), Phase 2 (escalate on low
    confidence or high/urgent priority), and Phase 3 (route a booking-shaped
    message to Booking Assistant instead of triaging it) all in one place --
    see this agent's CLAUDE.md "Flow" section for why these three phases
    share one code path rather than being separate endpoints.
    """
    intent = _detect_intent(message)

    # Phase 3: a booking-shaped message ("I'd like to book a call", "can I
    # reschedule") skips classification entirely and hands off to Booking
    # Assistant -- reuses rag/pipeline.py's existing keyword-based
    # _detect_intent (root CLAUDE.md convention #1: don't reimplement
    # intent detection a second time here) rather than asking the LLM to
    # judge it as part of the classification JSON above.
    if intent == "booking":
        ticket = _get_or_create_ticket(db, session_id, customer_email)
        ticket.category = "booking"
        db.add(TicketMessage(ticket_id=ticket.id, role="user", content=message))
        reply = "Sure -- let me find some times that could work."
        db.add(TicketMessage(ticket_id=ticket.id, role="agent", content=reply))
        db.commit()
        return ChatMessageResult(
            reply=reply, escalated=False, ticket_id=str(ticket.id), suggest_booking_flow=True
        )

    ticket = _get_or_create_ticket(db, session_id, customer_email)
    db.add(TicketMessage(ticket_id=ticket.id, role="user", content=message))

    escalated = False
    try:
        context = _retrieve_context(db, message)
        classification = await _classify(message, context)
        ticket.category = classification.category
        ticket.priority = classification.priority
        ticket.confidence = classification.confidence

        # Enforced here in code, not left to the LLM's own prompt-following
        # -- the system prompt already asks it to be honest at low
        # confidence, but trusting that alone means one off-instruction
        # response hands a visitor a hallucinated answer anyway.
        low_confidence = classification.confidence < settings.support_agent_confidence_threshold
        urgent = classification.priority in ("high", "urgent")
        if low_confidence or urgent:
            escalated = True
            ticket.status = "escalated"
            reply = (
                "I'm not confident I can answer that correctly -- I'll have someone from our "
                "team follow up with you."
                if low_confidence
                else "Thanks for flagging this -- I'm looping in our team right away so they can help."
            )
        else:
            reply = classification.answer
    except Exception:
        # Covers both ClassificationError (malformed JSON back from the
        # LLM) and any other failure (network, rate limit, timeout) --
        # never leave the visitor without a reply if this step fails, same
        # "apologize, don't crash the conversation" convention as
        # agents_voice.py's _handle_turn. Treated as escalation-worthy too:
        # a visitor whose message the AI couldn't even process should still
        # reach a human, not silently fall through the cracks.
        escalated = True
        ticket.status = "escalated"
        reply = "Sorry, I'm having trouble understanding right now. I'll have someone from our team follow up with you."

    db.add(TicketMessage(ticket_id=ticket.id, role="agent", content=reply))
    db.commit()

    if escalated:
        await notify_support_escalation(ticket)

    return ChatMessageResult(reply=reply, escalated=escalated, ticket_id=str(ticket.id))


@dataclass
class TicketResult:
    ticket_id: str
    status: str  # "open" | "escalated"


async def create_ticket(
    db: Session, channel: str, customer_name: str, customer_phone: str, issue_description: str
) -> TicketResult:
    """Exposed as a plain importable function for Voice Receptionist to call
    directly (same-process function call, not HTTP -- see apps/agents/
    CLAUDE.md, "How the three agents talk to each other") when a caller has
    an issue needing human follow-up.

    Always escalates immediately: Voice Receptionist has already decided,
    on its own, that this needs a human (that's why it's calling this
    function at all) -- re-running this agent's own LLM classification on
    top of that decision would be second-guessing a judgment already made,
    not adding useful signal.
    """
    ticket = Ticket(
        session_id=f"voice:{customer_phone}",
        channel=channel,
        status="escalated",
        customer_name=customer_name,
        customer_phone=customer_phone,
    )
    db.add(ticket)
    db.flush()
    db.add(TicketMessage(ticket_id=ticket.id, role="user", content=issue_description))
    db.commit()

    await notify_support_escalation(ticket)

    return TicketResult(ticket_id=str(ticket.id), status="escalated")
