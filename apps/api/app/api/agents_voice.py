"""
Voice Receptionist -- Phase 0 through Phase 4 (see
apps/agents/voice-receptionist/CLAUDE.md for the full phased plan).

Phase 0 proved the Twilio webhook round-trip works. Phase 1 added the
actual conversation loop. Phase 4 (agent-to-agent handoff) is this file's
newest piece: real tool-calling lets the LLM actually check availability
and create a real booking mid-call via app/services/booking_service.py --
the same core logic the chat widget's Booking Assistant uses -- instead of
just talking about scheduling with nothing behind it (confirmed live,
before this: a real test call ended with the agent promising "I'll email
you a scheduling link" and no email or calendar event was ever created).

WHY THIS FILE LIVES IN apps/api, NOT apps/agents/voice-receptionist:
see the module docstring history in git -- unchanged from Phase 0: Twilio
needs one running HTTP server, and apps/api is the "shared modular agent
process" apps/agents/CLAUDE.md describes.
"""

import asyncio
import json
import logging
import re
import time
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import HTMLResponse, Response
from pydantic import BaseModel
from sqlalchemy.orm import Session
from twilio.request_validator import RequestValidator
from twilio.twiml.voice_response import VoiceResponse, Gather

from mielikkix_agent_core import LLMClient, ToolCall

from ..core.config import settings
from ..core.database import get_db
from ..core.limiter import limiter
from ..integrations.google_calendar_client import GoogleCalendarError
from ..notifications import notify_new_booking
from ..rag.embeddings import embed_query
from ..rag.language_detect import detect_message_language
from ..rag.pipeline import retrieve_chunks, retrieve_faqs, retrieve_products
from ..services import booking_service, support_service

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/agents/voice", tags=["voice-receptionist"])

# English is always the FIRST language of a new call -- there's no way to know
# a caller's language before they've said anything (see the language-latch
# comment in _handle_turn) -- so the greeting stays English, with one short
# added line letting a Norwegian speaker know they can just go ahead in
# Norwegian instead of forcing a bilingual (and TTS-mispronounced) greeting.
_GREETING = "Hello, thanks for calling Mielikkix. How can I help you today? You can also speak with me in Norwegian."
_CLOSING_LINE = "Thanks for calling Mielikkix. Have a great day, goodbye!"
_CLOSING_LINE_NO = "Takk for at du ringte Mielikkix. Ha en fin dag, ha det bra!"
_SILENCE_CLOSING_LINE = "I haven't heard anything for a bit, so I'll let you go -- feel free to call back anytime. Goodbye!"
_SILENCE_CLOSING_LINE_NO = "Jeg har ikke hørt noe på en stund, så jeg lar deg gå -- ring gjerne tilbake når som helst. Ha det!"
_TURN_CAP_CLOSING_LINE = "We've covered a lot today -- I'll have someone from the team follow up on anything else. Thanks for calling Mielikkix, goodbye!"
_TURN_CAP_CLOSING_LINE_NO = "Vi har vært gjennom mye i dag -- jeg lar noen fra teamet følge opp resten. Takk for at du ringte Mielikkix, ha det!"
_NO_SPEECH_RETRY = "Sorry, I didn't catch that. Could you say that again?"
_NO_SPEECH_RETRY_NO = "Beklager, jeg fikk ikke med meg det. Kan du si det igjen?"
_LLM_ERROR_FALLBACK = "Sorry, I'm having trouble understanding right now. Could you try again in a moment?"
_LLM_ERROR_FALLBACK_NO = "Beklager, jeg har litt problemer med å forstå akkurat nå. Kan du prøve igjen om litt?"

_SYSTEM_PROMPT_BASE = (
    "You are a warm, professional voice receptionist answering a phone call "
    "for Mielikkix. Keep replies short (1-3 sentences) and conversational, "
    "since this is a spoken phone call, not a chat window -- long replies "
    "are tedious to listen to.\n\n"
    "IMPORTANT: 'Mielikkix' is an invented brand name, and speech-to-text "
    "(both Twilio's on a real call, and the caller's browser in a demo) "
    "frequently mishears it as something phonetically similar -- 'Millie "
    "Cakes', 'Millie kicks', 'melee cakes', 'me a licks', and similar. If "
    "the caller asks about a business/company/product with an unfamiliar "
    "name that sounds close to 'Mielikkix', assume they mean Mielikkix "
    "itself and answer normally -- do NOT treat it as a real, different, "
    "unknown company you have no information about."
)

# Appended to every system prompt (booking has nothing to do with whether
# RAG found business context, so this isn't conditional on that) --
# instructs the LLM on the real tools it has (see _VOICE_TOOLS
# below), and enforces the "always get an explicit yes" rule at the prompt
# level too, not just the server-side _CONFIRMATION_PATTERN gate in
# _execute_tool -- belt and suspenders, since Twilio's speech-to-text is
# not perfectly reliable and a wrongly-created real calendar event is a
# worse failure than one extra confirmation exchange.
_BOOKING_SYSTEM_PROMPT_ADDENDUM = (
    "\n\nYou can also help callers book a real appointment. Use the "
    "check_availability tool as soon as you know roughly what they want to "
    "book and roughly when -- you don't need an exact date or time first. "
    "When it returns options, read out at most 2-3 of them using their "
    "'spoken' text exactly as given (never read out a raw date/time "
    "yourself) and ask which works. Once the caller has picked one AND "
    "given you a name and email, call propose_booking with those details "
    "-- do NOT compose your own confirmation question yourself. "
    "propose_booking's own result IS what gets said next, verbatim: it "
    "reads the slot/name/email back and explicitly asks whether the email "
    "is correct before asking to book, which catches a misheard email "
    "(confirmed live) better than you moving straight to 'shall I book "
    "it?' would. If the caller corrects a detail after hearing it read "
    "back, call propose_booking again with the corrected value -- never "
    "invent a name or email; ask for them if you don't have them yet.\n\n"
    "If the caller has an issue, complaint, or question you cannot resolve "
    "yourself -- a billing dispute, a technical problem, or anything you're "
    "not confident you've fully addressed -- use the create_support_ticket "
    "tool so a real person follows up. Get their name first if you don't "
    "already have it. Tell them a member of the team will be in touch."
)

# Appended once _call_language has latched onto "no" for this call (see
# _handle_turn) -- everything else in the system prompt stays in English
# (LLMs follow English instructions about a non-English OUTPUT language
# just fine; translating the instructions themselves would be extra work
# for no behavioral benefit). Deterministic, non-LLM lines (greeting,
# closings, the propose_booking confirmation text, etc.) are switched
# separately -- see the _NO-suffixed constants throughout this file.
_LANGUAGE_INSTRUCTION_NO = (
    "\n\nIMPORTANT: The caller is speaking Norwegian. From this point on, "
    "reply ONLY in Norwegian (Bokmål) -- never switch back to English mid-"
    "call, even though these instructions themselves are in English."
)


_WEEKDAYS_NO = {
    "Monday": "mandag",
    "Tuesday": "tirsdag",
    "Wednesday": "onsdag",
    "Thursday": "torsdag",
    "Friday": "fredag",
    "Saturday": "lørdag",
    "Sunday": "søndag",
}


def _format_slot_for_speech(slot_start: datetime, language: str = "en") -> str:
    """"Tuesday at 2 PM" style (or, for language="no", "tirsdag klokken
    14:00" -- Norwegian convention is a 24-hour clock, not AM/PM), in the
    fixed voice-booking timezone (see _VOICE_BOOKING_TIMEZONE below) -- the
    LLM reads this exact string aloud rather than being handed a raw
    ISO/UTC timestamp to convert and speak itself, which would risk it
    mis-converting the timezone or misreading digits. `strftime("%A")`
    itself is locale-independent (always English) regardless of Python's
    process-wide locale, so the Norwegian day name is a plain lookup here
    rather than a global locale switch, which isn't thread-safe."""
    local = slot_start.astimezone(ZoneInfo(_VOICE_BOOKING_TIMEZONE))
    if language == "no":
        day = _WEEKDAYS_NO[local.strftime("%A")]
        return f"{day} klokken {local.strftime('%H:%M')}"
    day = local.strftime("%A")
    time_part = (
        local.strftime("%I %p").lstrip("0")
        if local.minute == 0
        else local.strftime("%I:%M %p").lstrip("0")
    )
    return f"{day} at {time_part}"


# A loose sanity check, not full RFC 5322 validation -- just enough to
# catch the shape of failure confirmed live: speech-to-text mangling
# "pratibhajobs10@gmail.com" into something like "pratibha jobstand at
# gmail.com" (the LITERAL WORD "at", no "@" at all), which propose_booking
# below used to accept and read back as garbled nonsense. Rejecting
# anything that doesn't look like `local@domain.tld` here means a caller
# gets asked to repeat a clearly-broken email immediately, deterministically,
# rather than confirming visible garbage.
_EMAIL_SHAPE_PATTERN = re.compile(r"^[^\s@]+@[^\s@]+\.[^\s@]+$")


# Booking Assistant's /request and /confirm routes take the VISITOR's own
# IANA timezone (from the browser) -- a phone call has no browser. Every
# .no-domain signal in this codebase (mielikkix.no, panthermedia.no,
# NOTIFICATION_FROM_EMAIL=post@mielikkix.no) points at a Norway-based
# business, and this is the same single-business scope boundary already
# accepted for RAG grounding (settings.voice_agent_business_id) -- applied
# here to booking too. The real permanent fix is a per-business
# BusinessSettings.timezone column (also fixing business_hours' own
# visitor-timezone quirk noted in notifications/__init__.py), deferred as
# separate scope.
_VOICE_BOOKING_TIMEZONE = "Europe/Oslo"

_CHECK_AVAILABILITY_TOOL = {
    "type": "function",
    "function": {
        "name": "check_availability",
        "description": (
            "Look up real open appointment slots for what the caller wants "
            "to book. Call this as soon as you know roughly what they want "
            "and roughly when -- an exact date/time isn't required."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "description": {
                    "type": "string",
                    "description": (
                        "The caller's request in their own words, e.g. "
                        "'30 minute consultation next Tuesday afternoon'."
                    ),
                }
            },
            "required": ["description"],
        },
    },
}

_PROPOSE_BOOKING_TOOL = {
    "type": "function",
    "function": {
        "name": "propose_booking",
        "description": (
            "Reads the chosen slot and the caller's name/email back to "
            "them, asks whether the email is correct, and asks 'shall I "
            "book it?' -- does NOT create the booking yet, only the "
            "caller's own next 'yes' does that. Call this once you know "
            "which slot number the caller wants and you have their name "
            "and email. The exact confirmation wording is generated for "
            "you; say it verbatim, don't add your own text before or "
            "after it."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "slot_index": {
                    "type": "integer",
                    "description": (
                        "The number (1, 2, ...) of the slot from the most "
                        "recent check_availability results the caller picked."
                    ),
                },
                "name": {"type": "string"},
                "email": {"type": "string"},
                "phone": {
                    "type": "string",
                    "description": (
                        "Optional -- omit if not given; the system already "
                        "has the caller's number from the call itself."
                    ),
                },
            },
            "required": ["slot_index", "name", "email"],
        },
    },
}

_CREATE_SUPPORT_TICKET_TOOL = {
    "type": "function",
    "function": {
        "name": "create_support_ticket",
        "description": (
            "Creates a support ticket for a human team member to follow up "
            "on. Use this when the caller has an issue, complaint, or "
            "question you cannot resolve yourself -- a billing dispute, a "
            "technical problem, or anything you're not confident you've "
            "fully addressed. Their phone number is already known from the "
            "call itself."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "customer_name": {"type": "string"},
                "issue_description": {
                    "type": "string",
                    "description": "A short summary of the caller's issue, in your own words.",
                },
            },
            "required": ["customer_name", "issue_description"],
        },
    },
}

_VOICE_TOOLS = [_CHECK_AVAILABILITY_TOOL, _PROPOSE_BOOKING_TOOL, _CREATE_SUPPORT_TICKET_TOOL]

# How many extra LLM round-trips one phone turn may spend on tool calls
# before giving up -- Twilio's own webhook response budget is on the order
# of ~15s (verify the current figure in Twilio's docs before relying on
# this), and each round-trip is a real Groq call plus, for
# check_availability, a real Google Calendar call. _llm_client below is
# built with a tighter per-call timeout than the module default
# specifically because of this chaining -- tune both numbers against real
# measured latency via /dev/voice-test, not this guess.
_MAX_TOOL_ROUNDS = 2
_TOOL_LOOP_FALLBACK = (
    "Let me have someone from the team follow up on the booking details so "
    "I don't keep you waiting -- is there anything else I can help with?"
)

# check_availability truncates to this many slots before they ever reach
# the model -- see _execute_tool's own comment on why this must happen
# before storing/returning them, not just as a hint for how many to read
# aloud.
_MAX_SPOKEN_SLOTS = 3

# Simple heuristic, not full intent classification (that's Phase 2+ per
# this agent's CLAUDE.md) -- just enough to let a caller end the call by
# saying so, instead of the loop continuing until they hang up the phone
# themselves or (in the browser demo) click Hang Up. Word-boundary matched
# for the same reason rag/pipeline.py's _matches_any is: a plain substring
# check on "bye" would misfire on "goodbye" being fine but also on
# unrelated words containing "bye"-like fragments in a longer sentence.
# Norwegian alternatives included in the SAME pattern (not a separate
# per-language regex) since this is checked against the caller's raw
# speech, before/independent of the language-latch logic in _handle_turn --
# a caller who has just switched to Norwegian saying "ha det" must still
# end the call correctly.
_GOODBYE_PATTERN = re.compile(
    r"\b(bye|goodbye|good bye|that'?s all|nothing else|no thanks|no that'?s it|"
    r"hang up|end the call|that'?s it for now|"
    r"ha det|hade|adjø|farvel|det var alt|ingenting mer|legg på)\b",
    re.IGNORECASE,
)

# Gates the deterministic finalize-booking step in _handle_turn (see
# _call_pending_confirmation below), checked against the raw caller speech
# for the turn immediately after propose_booking ran -- not turn-count
# bookkeeping otherwise, and not re-parsed from an LLM tool call at all
# anymore. An earlier version (when book_appointment created the booking
# directly) tracked "was book_appointment called in the same turn as
# check_availability" instead, but that broke on a real, legitimate flow
# (confirmed live): the model redundantly re-called check_availability to
# double-check a slot it had already offered in an earlier turn, then tried
# to book in that same turn -- the re-check stamped "just checked" over the
# ORIGINAL turn, making an already-confirmed booking look same-turn and get
# wrongly refused. Checking the caller's own words for the turn right after
# propose_booking's readback avoids that fragility entirely.
# Norwegian alternatives included in the same pattern, same reasoning as
# _GOODBYE_PATTERN above -- a Norwegian-speaking caller confirming a
# booking says "ja"/"stemmer"/"bestill", not "yes"/"confirm".
_CONFIRMATION_PATTERN = re.compile(
    r"\b(yes|yeah|yep|yup|sure|go ahead|book it|please book|confirm|"
    r"that works|sounds good|correct|do it|book that|please do|"
    r"ja|jepp|jada|korrekt|riktig|stemmer|bestill|det stemmer)\b",
    re.IGNORECASE,
)

# How many consecutive silent turns (caller said nothing, <Gather> timed
# out) before the call ends itself -- otherwise someone who walked away
# without hanging up leaves the call (and, on a real Twilio call, the
# per-minute billing) running indefinitely.
_MAX_CONSECUTIVE_SILENCES = 2
_call_silence_counts: dict[str, int] = {}

# Caps how many LLM (Groq) calls a single call/session can make before the
# receptionist wraps up on its own -- the silence-cap and goodbye-phrase
# checks above only end the call if the caller goes quiet or says so, so a
# caller who just keeps talking would otherwise generate an unbounded
# number of paid LLM calls on one open phone line. Only real turns that
# actually reach the LLM count -- a silent/no-speech turn doesn't call it,
# so it doesn't count against this either.
_MAX_TURNS_PER_CALL = 30
_call_turn_counts: dict[str, int] = {}

# --- Grounding a mis-heard/clipped question about Mielikkix itself ---
#
# This went through three narrower versions before landing here, each
# defeated by real testing:
#   1. An exact-match list of known mishearings ("Millie Cakes", "milky
#      cakes", ...) -- doesn't scale, there's no way to enumerate every way
#      a recognizer can mangle an invented word.
#   2. Anchoring "Mielikkix" onto the query whenever it looked like a
#      "what is / tell me about / know about <X>"-shaped question -- missed
#      real phrasing ("would like to know about"), and broke entirely when
#      speech recognition clipped the leading words off completely (e.g.
#      "what is mini cakes" -> just "mini cakes" reached the server, no
#      question-shape left to detect at all).
#   3. Anchoring + a looser confidence threshold for anchored queries --
#      turned out the anchor word "Mielikkix" alone inflates every
#      candidate's similarity score into roughly the same range regardless
#      of actual relevance (measured: "Mielikkix tell me a joke" scored
#      0.32, "Mielikkix mini cakes" scored 0.25 -- no meaningful gap to set
#      a threshold in). Confidence-score gating just doesn't work once the
#      query has been anchored.
#
# The actual fix: this is Mielikkix's OWN phone line. ANY question that
# doesn't already name Mielikkix gets it anchored on, unconditionally --
# no shape-matching to get wrong -- and once anchored, retrieval skips the
# confidence gate entirely and just hands the LLM the real top-k content.
# There's no reliable score left to gate on anyway (see point 3), and the
# system prompt already instructs the LLM to only use what's actually
# relevant and admit it plainly when nothing here answers the question --
# that judgment call belongs to the LLM reading the real content, not a
# similarity score computed before the content was even retrieved.
def _anchor_query_for_retrieval(speech: str) -> str:
    if "mielikkix" in speech.lower():
        return speech
    return f"Mielikkix {speech}"


# Best-effort DISPLAY correction for the browser demo's transcript --
# rewrites the caller's own chat bubble to show "Mielikkix" instead of the
# mishearing, live. This is NOT what makes retrieval actually work (that's
# the unconditional anchoring above, which handles any mishearing, seen
# before or not, and any clipped question shape) -- this list only covers
# mishearings actually observed in testing. A new one just means the
# display doesn't get prettied up for it yet, not that the agent stops
# answering correctly; the two are deliberately decoupled so display polish
# never gates correctness. Not used for the real Twilio call flow at all --
# a phone call has no transcript UI to correct.
_KNOWN_MISHEARING_DISPLAY_PATTERN = re.compile(
    r"\b(millie\s*cakes?|milky\s*cakes?|milk\s*cakes?|mila\s*cakes?|mini\s*cakes?|melee\s*cakes?|"
    r"millie\s*kicks?|milli\s*kicks?|mealy\s*kicks?|me\s*a\s*licks?)\b",
    re.IGNORECASE,
)


def _display_correction(speech: str) -> str | None:
    """Corrected version of what the caller said, for the browser demo's
    transcript, if a known mishearing is found -- None if nothing
    recognized (the raw transcript is shown as-is, uncorrected)."""
    corrected = _KNOWN_MISHEARING_DISPLAY_PATTERN.sub("Mielikkix", speech)
    return corrected if corrected != speech else None


_RAG_TOP_K = 4
# A sanity floor, not a relevance gate (see the long comment above for why
# a real relevance threshold doesn't work once the query is anchored) --
# just enough to drop literal zero/negative-similarity noise, not to judge
# whether a match is "good enough".
_RAG_MINIMUM_SCORE = 0.05


def _retrieve_context(db: Session, query: str) -> str:
    """Grounds the reply in settings.voice_agent_business_id's actual
    FAQs/documents/products -- reuses the exact same retrieval functions
    the Chat Widget's RAG pipeline uses (rag/pipeline.py), rather than
    reimplementing embedding/scoring a second time. `query` is expected to
    already be anchored to Mielikkix by the caller (see
    _anchor_query_for_retrieval) -- returns "" only if no business is
    configured at all, or literally nothing scores above noise level.
    """
    if not settings.voice_agent_business_id:
        return ""

    query_embedding = embed_query(query)
    matches = (
        retrieve_chunks(db, settings.voice_agent_business_id, query_embedding, _RAG_TOP_K)
        + retrieve_faqs(db, settings.voice_agent_business_id, query_embedding)
        + retrieve_products(db, settings.voice_agent_business_id, query_embedding)
    )
    return "\n\n".join(text for text, score in matches if score >= _RAG_MINIMUM_SCORE)


def _build_system_prompt(context: str, language: str = "en") -> str:
    if context:
        base = (
            f"{_SYSTEM_PROMPT_BASE}\n\nUse the following real information about "
            f"Mielikkix to answer the caller's question. If the answer isn't in "
            f"this information, say so plainly and offer to have someone follow "
            f"up, rather than guessing or inventing details.\n\n{context}"
        )
    else:
        base = (
            f"{_SYSTEM_PROMPT_BASE} You don't currently have access to specific "
            f"business information for this question, so say so plainly and offer "
            f"to have someone follow up, rather than guessing."
        )
    base += _BOOKING_SYSTEM_PROMPT_ADDENDUM
    if language == "no":
        base += _LANGUAGE_INSTRUCTION_NO
    return base

# Python note: a plain module-level dict, not a database table. This is
# Phase 1 scope only -- "just a friendly echo/conversation," per this
# agent's CLAUDE.md. Real transcript/summary persistence to packages/db
# is a later phase (see that CLAUDE.md's "Wrap-up" phase); this dict is
# just enough in-process memory to keep one call's turns coherent, and it
# resets on every server restart -- fine for now, wrong for production.
_call_history: dict[str, list[dict]] = {}

# A real phone call has no explicit "it's over" signal on this end beyond
# the goodbye/silence-cap paths in _handle_turn -- someone who just hangs up
# the phone (or a /dev caller who closes the browser tab) leaves their entry
# here forever otherwise, one small leak per call, unbounded over time.
# _touch_call/_forget_call/_evict_stale_calls bound that: anything not
# touched in _CALL_STATE_TTL_SECONDS is swept on the next turn.
_CALL_STATE_TTL_SECONDS = 30 * 60
_call_last_seen: dict[str, float] = {}

# Which language this call is currently running in -- "en" (the implicit
# default, never actually stored until switched) or "no", set by the
# language-latch logic in _handle_turn. Swept by the same TTL/forget
# mechanism as the rest of this call's state.
_call_language: dict[str, str] = {}

# Booking's own per-call state, swept by the same TTL/forget mechanism as
# the conversation state above.
_call_pending_slots: dict[str, list[booking_service.SlotOption]] = {}
_call_pending_meeting_type: dict[str, str] = {}
# Set by propose_booking (_execute_tool), consumed by _handle_turn's
# pending-confirmation fast path -- slot_index/name/email/phone exactly as
# read back to the caller, plus the turn_count propose_booking ran on.
# Single-shot and turn-scoped on purpose: valid ONLY if the very next real
# turn is the one that confirms it (see _handle_turn), so a stale proposal
# nobody answered can never get accidentally triggered by an unrelated
# "yes" several turns later.
_call_pending_confirmation: dict[str, dict] = {}
# Twilio's own `From` field on the incoming call -- captured once in
# voice_incoming, never from speech-to-text, so propose_booking/
# _finalize_booking has a verified phone number to fall back on if the
# caller doesn't state one.
_call_caller_number: dict[str, str] = {}


def _touch_call(call_sid: str) -> None:
    _call_last_seen[call_sid] = time.monotonic()


def _forget_call(call_sid: str) -> None:
    _call_last_seen.pop(call_sid, None)
    _call_history.pop(call_sid, None)
    _call_silence_counts.pop(call_sid, None)
    _call_turn_counts.pop(call_sid, None)
    _call_language.pop(call_sid, None)
    _call_pending_slots.pop(call_sid, None)
    _call_pending_meeting_type.pop(call_sid, None)
    _call_pending_confirmation.pop(call_sid, None)
    _call_caller_number.pop(call_sid, None)


def _evict_stale_calls() -> None:
    cutoff = time.monotonic() - _CALL_STATE_TTL_SECONDS
    stale = [sid for sid, last_seen in _call_last_seen.items() if last_seen < cutoff]
    for sid in stale:
        _forget_call(sid)


# Voice Receptionist's model tier: OpenAI (settings.openai_model, default
# gpt-4o) -- standard chat-completions-with-tools, the same turn-based
# Gather/Say flow this module already runs, NOT OpenAI's separate Realtime
# (audio-streaming) API. Real-time voice would mean replacing Twilio's
# <Gather>/<Say> webhook round-trip with Twilio Media Streams + a
# persistent WebSocket audio session end to end -- a genuinely different
# architecture, not a provider swap, and deliberately out of scope here so
# a live product path isn't rearchitected unattended; this swap only gets
# Voice Receptionist off Groq (which was rate-limiting badly enough to
# stall live calls -- see llm_client.py's own retry-fix comment) to a
# provider with real capacity for the SAME text-turn flow.
#
# A tighter per-call timeout than LLMClient's own 15s default: a single
# turn can now chain up to _MAX_TOOL_ROUNDS+1 LLM calls plus a real Google
# Calendar call (inside check_availability), and Twilio's own webhook
# response budget is itself only ~15s total for the whole turn -- verify
# both numbers against real measured latency via /dev/voice-test rather
# than trusting this guess.
_llm_client = LLMClient(provider="openai", timeout_seconds=8.0)

# Fire-and-forget booking-notification tasks (see _fire_booking_notification)
# need a kept reference or asyncio can garbage-collect a running task mid-
# send -- there's no FastAPI BackgroundTasks available in a Twilio webhook
# handler the way agents_booking.py's HTTP route has, so this module owns
# its own equivalent.
_pending_notification_tasks: set[asyncio.Task] = set()


def _fire_booking_notification(result: booking_service.ConfirmBookingResult) -> None:
    if not result.notify_email:
        return
    task = asyncio.create_task(notify_new_booking(result.notify_email, result.booking))
    _pending_notification_tasks.add(task)
    task.add_done_callback(_pending_notification_tasks.discard)


async def _execute_tool(
    db: Session, call_sid: str, turn_count: int, speech: str, tool_call: ToolCall, language: str
) -> str:
    """Runs one tool the LLM asked for and returns its result as a JSON
    string -- the shape `role: "tool"` messages need (see _handle_turn).
    Never raises: GoogleCalendarError becomes a plain {"status":
    "calendar_error"} result so the LLM apologizes gracefully instead of
    crashing the whole call turn.
    """
    try:
        args = json.loads(tool_call.arguments)
    except (json.JSONDecodeError, TypeError):
        logger.info("call=%s turn=%s tool=%s invalid_arguments raw=%r", call_sid, turn_count, tool_call.name, tool_call.arguments)
        return json.dumps({"status": "invalid_arguments"})

    logger.info("call=%s turn=%s tool=%s args=%s", call_sid, turn_count, tool_call.name, args)

    if tool_call.name == "check_availability":
        try:
            result = await booking_service.resolve_booking_request(
                db, args.get("description", ""), _VOICE_BOOKING_TIMEZONE, None
            )
        except GoogleCalendarError:
            logger.info("call=%s turn=%s check_availability calendar_error", call_sid, turn_count)
            return json.dumps({"status": "calendar_error"})

        logger.info("call=%s turn=%s check_availability -> status=%s slots=%d", call_sid, turn_count, result.status, len(result.slots))

        if result.status != "needs_selection":
            return json.dumps(
                {"status": result.status, "clarification_question": result.clarification_question}
            )

        # Truncate BEFORE storing, not just before speaking -- confirmed
        # live as a real bug: resolve_booking_request can return up to 8
        # slots, but the system prompt only asks the model to read 2-3
        # aloud. When all 8 were included in the tool result, the model
        # sometimes renumbered "1, 2" in its own spoken prose to match
        # whichever ones it chose to mention, which didn't line up with
        # their REAL index in the full list -- so propose_booking(index=1)
        # could silently stage a completely different slot than the one the
        # caller actually heard and agreed to. Storing the same truncated
        # list propose_booking/_finalize_booking look up from makes that
        # mismatch impossible: index 1 in the tool result and index 1 in
        # _call_pending_slots are now guaranteed to be the same slot.
        spoken_slots = result.slots[:_MAX_SPOKEN_SLOTS]
        _call_pending_slots[call_sid] = spoken_slots
        _call_pending_meeting_type[call_sid] = result.meeting_type or "appointment"
        return json.dumps(
            {
                "status": "needs_selection",
                "meeting_type": result.meeting_type,
                "duration_minutes": result.duration_minutes,
                "slots": [
                    {"index": i + 1, "spoken": _format_slot_for_speech(slot.start, language)}
                    for i, slot in enumerate(spoken_slots)
                ],
            }
        )

    if tool_call.name == "propose_booking":
        # Doesn't book anything -- only stages _call_pending_confirmation
        # and hands back the exact deterministic text to say next (see
        # _handle_turn's tool-round loop, which speaks this verbatim
        # instead of letting the model paraphrase it). The actual booking
        # only happens if the caller's OWN next turn passes
        # _CONFIRMATION_PATTERN, checked in _handle_turn against their raw
        # speech -- never re-derived from another LLM tool call, which is
        # exactly the risk this whole propose/finalize split exists to
        # remove (a model that garbles or re-invents slot/name/email on a
        # second call would silently book the wrong thing).
        slots = _call_pending_slots.get(call_sid, [])
        slot_index = args.get("slot_index")
        # LLM-generated JSON isn't guaranteed to emit a number as a JSON
        # number rather than a numeric string (e.g. "1" instead of 1) --
        # untrusted input from this app's own perspective either way (same
        # reasoning as agents_booking.py's own LLM-output handling), so
        # coerce a clean numeric string before rejecting it outright.
        if isinstance(slot_index, str) and slot_index.strip().isdigit():
            slot_index = int(slot_index.strip())
        if not isinstance(slot_index, int) or not (1 <= slot_index <= len(slots)):
            logger.info("call=%s turn=%s propose_booking invalid_slot_index=%r (have %d slots)", call_sid, turn_count, slot_index, len(slots))
            return json.dumps({"status": "invalid_slot_index"})

        name, email = args.get("name"), args.get("email")
        if not name or not email:
            logger.info("call=%s turn=%s propose_booking missing_details name=%r email=%r", call_sid, turn_count, name, email)
            return json.dumps({"status": "missing_details"})
        # Confirmed live: speech-to-text can mangle an email badly enough
        # that what the model extracted isn't even shaped like one anymore
        # (e.g. "pratibha jobstand at gmail.com" -- the literal word "at",
        # no "@"). Catching that HERE, deterministically, means the caller
        # gets asked to repeat it immediately instead of the confirmation
        # step reading back visible garbage.
        if not _EMAIL_SHAPE_PATTERN.match(email):
            logger.info("call=%s turn=%s propose_booking malformed_email=%r", call_sid, turn_count, email)
            return json.dumps(
                {
                    "status": "invalid_email",
                    "message": "That doesn't sound like a complete email address. Ask the caller to say it again slowly.",
                }
            )

        chosen = slots[slot_index - 1]
        _call_pending_confirmation[call_sid] = {
            "turn": turn_count,
            "slot_index": slot_index,
            "name": name,
            "email": email,
            "phone": args.get("phone"),
        }
        # Read back normally (not spelled out) but as an explicit yes/no
        # question specifically about the email -- confirmed live that
        # character-by-character spelling, while unambiguous, made a real
        # conversation painfully slow to follow and hard to correct
        # mid-stream. The email-shape check above already catches the
        # worst failure mode (a structurally broken email); this question
        # is the caller's chance to catch a well-formed-but-wrong one
        # (right shape, wrong person -- e.g. a misheard digit inside a
        # plausible-looking address).
        if language == "no":
            confirmation_text = (
                f"Bare for å bekrefte: {_format_slot_for_speech(chosen.start, language)} for {name}, "
                f"og jeg har e-posten din som {email}. Stemmer det? Skal jeg booke den?"
            )
        else:
            confirmation_text = (
                f"Just to confirm: {_format_slot_for_speech(chosen.start)} for {name}, "
                f"and I have your email as {email}. Is that correct? Shall I book it?"
            )
        logger.info("call=%s turn=%s propose_booking -> awaiting_confirmation slot=%s email=%s", call_sid, turn_count, slot_index, email)
        return json.dumps({"status": "awaiting_confirmation", "say": confirmation_text})

    if tool_call.name == "create_support_ticket":
        customer_name = args.get("customer_name")
        issue_description = args.get("issue_description")
        if not customer_name or not issue_description:
            logger.info(
                "call=%s turn=%s create_support_ticket missing_details name=%r issue=%r",
                call_sid, turn_count, customer_name, issue_description,
            )
            return json.dumps({"status": "missing_details"})

        result = await support_service.create_ticket(
            db,
            channel="voice",
            customer_name=customer_name,
            customer_phone=_call_caller_number.get(call_sid, ""),
            issue_description=issue_description,
        )
        logger.info("call=%s turn=%s create_support_ticket -> ticket=%s status=%s", call_sid, turn_count, result.ticket_id, result.status)
        return json.dumps({"status": result.status, "ticket_id": result.ticket_id})

    logger.info("call=%s turn=%s unknown_tool=%s", call_sid, turn_count, tool_call.name)
    return json.dumps({"status": "unknown_tool"})


async def _finalize_booking(db: Session, call_sid: str, turn_count: int, pending: dict, language: str) -> str:
    """Actually creates the booking staged by propose_booking, once
    _handle_turn has confirmed the caller's very next turn said yes.
    Deliberately does NOT go back through the LLM for slot_index/name/email
    -- those are exactly what propose_booking already read back to the
    caller verbatim (see _execute_tool); re-deriving them from a second
    tool call would reopen the misheard-detail risk this whole split
    exists to close. Only the confirmation reply itself is deterministic
    prose, same reasoning as propose_booking's own confirmation_text.
    """
    slots = _call_pending_slots.get(call_sid, [])
    slot_index = pending["slot_index"]
    if not (1 <= slot_index <= len(slots)):
        # Slots are only ever cleared by a completed booking or a fresh
        # check_availability call (see _execute_tool/_start_call) -- this
        # can only happen if the caller asked to check availability again
        # for something else between propose_booking and now, which
        # replaced the list propose_booking's slot_index pointed into.
        logger.info("call=%s turn=%s finalize_booking stale_slot_index=%s (have %d slots)", call_sid, turn_count, slot_index, len(slots))
        if language == "no":
            return "Beklager, den timen er ikke tilgjengelig lenger -- kan du si hva du vil booke på nytt?"
        return "Sorry, that slot isn't available anymore -- could you tell me what you'd like to book again?"

    chosen = slots[slot_index - 1]
    try:
        result = await booking_service.confirm_booking_slot(
            db,
            None,
            chosen.start,
            chosen.end,
            _VOICE_BOOKING_TIMEZONE,
            pending["name"],
            pending["email"],
            pending.get("phone") or _call_caller_number.get(call_sid),
            _call_pending_meeting_type.get(call_sid, "appointment"),
            call_sid,
        )
    except GoogleCalendarError:
        logger.info("call=%s turn=%s finalize_booking calendar_error", call_sid, turn_count)
        if language == "no":
            return "Beklager, jeg fikk ikke kontakt med kalenderen akkurat nå -- kan vi prøve igjen om litt?"
        return "Sorry, I couldn't reach the calendar just now -- could we try that again in a moment?"

    logger.info("call=%s turn=%s finalize_booking -> status=%s", call_sid, turn_count, result.status)

    if result.status == "booked":
        _fire_booking_notification(result)
        _call_pending_slots.pop(call_sid, None)
        _call_pending_meeting_type.pop(call_sid, None)
        if language == "no":
            return (
                f"Da er du booket -- jeg har booket {_format_slot_for_speech(chosen.start, language)}. "
                f"En kalenderinvitasjon er på vei til {pending['email']}."
            )
        return (
            f"You're all set -- I've booked {_format_slot_for_speech(chosen.start)}. "
            f"A calendar invite is on its way to {pending['email']}."
        )
    if result.status == "conflict":
        if language == "no":
            return "Beklager, den timen ble akkurat tatt av noen andre -- vil du at jeg skal sjekke ledige tider igjen?"
        return "Sorry, that slot was just taken by someone else -- would you like me to check availability again?"
    if language == "no":
        return "Beklager, noe gikk galt med bookingen -- kan vi prøve igjen om litt?"
    return "Sorry, something went wrong booking that -- could we try again in a moment?"


def _assert_valid_twilio_request(request: Request, form: dict) -> None:
    """See Phase 0's version of this function for the full explanation --
    unchanged here, just reused by both routes below."""
    if not settings.twilio_auth_token:
        return

    validator = RequestValidator(settings.twilio_auth_token)
    signature = request.headers.get("X-Twilio-Signature", "")
    called_url = f"{settings.voice_agent_public_base_url.rstrip('/')}{request.url.path}"
    if not validator.validate(called_url, form, signature):
        raise HTTPException(status_code=403, detail="Invalid Twilio signature")


async def _handle_turn(db: Session, call_sid: str, speech: str) -> tuple[str, bool]:
    """Core conversation turn: given what the caller said, returns (what
    the receptionist should say back, whether the call should end after
    saying it). Shared by the real Twilio-facing /gather route below AND
    the local-only /dev/gather route (browser mic test page) further down
    -- the actual conversation logic exists in exactly one place, and both
    interfaces just format its result differently (TwiML XML with a
    <Hangup/>, vs. plain JSON with an `ended` flag).

    Phase 4/5: the single LLM call is now a bounded tool-calling loop -- the
    model may ask to run check_availability/propose_booking/
    create_support_ticket (see _VOICE_TOOLS) before returning the plain text
    it actually says aloud. propose_booking is a special case: its own
    result text is spoken directly (see the tool-round loop below), never
    handed back to the model to paraphrase, and if THIS turn is a caller's
    "yes" to a booking propose_booking staged last turn, the whole LLM call
    is skipped entirely in favor of _finalize_booking -- see the pending-
    confirmation check right after `history.append` below.
    Only the final text is persisted to `history`; the intermediate
    tool-call/tool-result messages live only in this turn's local
    `messages` list and are discarded once the turn ends -- replaying raw
    tool JSON across turns would bloat context for no benefit, since the
    LLM already said the outcome aloud in plain language.
    """
    _evict_stale_calls()
    _touch_call(call_sid)

    speech = speech.strip()
    history = _call_history.setdefault(call_sid, [])

    # One-directional latch: once a turn's speech scores as Norwegian, the
    # call stays in Norwegian for everything after -- never auto-flips back
    # to English on a later turn that happens to score ambiguously (a bare
    # "ja" doesn't score as English either), which would whiplash the
    # caller mid-conversation. Reuses the exact same heuristic
    # rag/language_detect.py already uses for the Chat Widget, rather than
    # a second, separate detector for voice.
    #
    # Known limitation: turn 1's <Gather> is still running English speech
    # recognition (see _gather's language param, chosen from _call_language
    # BEFORE this function ever runs on that turn) -- a caller who launches
    # straight into a full Norwegian sentence may get a badly mis-
    # transcribed first turn, so the switch often only catches reliably
    # once the caller says something short and clearly Norwegian ("hei",
    # "ja", the word "norsk" itself). From turn 2 onward, once switched,
    # Gather's own recognition language is nb-NO too, so full Norwegian
    # sentences transcribe properly.
    if speech and _call_language.get(call_sid) != "no":
        if detect_message_language(speech, ["en", "no"], default="en") == "no":
            _call_language[call_sid] = "no"
    language = _call_language.get(call_sid, "en")

    if not speech:
        silence_count = _call_silence_counts.get(call_sid, 0) + 1
        _call_silence_counts[call_sid] = silence_count
        if silence_count >= _MAX_CONSECUTIVE_SILENCES:
            _forget_call(call_sid)
            return (_SILENCE_CLOSING_LINE_NO if language == "no" else _SILENCE_CLOSING_LINE), True
        return (_NO_SPEECH_RETRY_NO if language == "no" else _NO_SPEECH_RETRY), False

    _call_silence_counts[call_sid] = 0  # any real speech resets the count

    if _GOODBYE_PATTERN.search(speech):
        _forget_call(call_sid)
        return (_CLOSING_LINE_NO if language == "no" else _CLOSING_LINE), True

    turn_count = _call_turn_counts.get(call_sid, 0) + 1
    _call_turn_counts[call_sid] = turn_count
    if turn_count > _MAX_TURNS_PER_CALL:
        _forget_call(call_sid)
        return (_TURN_CAP_CLOSING_LINE_NO if language == "no" else _TURN_CAP_CLOSING_LINE), True

    history.append({"role": "user", "content": speech})

    # Deterministic finalize-booking fast path: propose_booking staged a
    # confirmation on some earlier turn, and this is the very next one --
    # if the caller's own raw words affirm it, book it now using exactly
    # what was already read back to them (never re-asking the LLM to
    # restate slot/name/email, which would reopen the misheard-detail risk
    # propose_booking's explicit "is that correct?" readback exists to
    # close), and skip the LLM call entirely for this turn. Single-shot:
    # popped here regardless of outcome, so a stale unanswered proposal
    # can never fire later on an unrelated "yes". A non-affirmative reply
    # here (a correction, a new question, anything else) just falls
    # through to the normal LLM turn
    # below with the proposal already cleared -- the model still has
    # propose_booking available to re-stage once it has corrected details.
    pending = _call_pending_confirmation.get(call_sid)
    if pending and pending["turn"] == turn_count - 1:
        _call_pending_confirmation.pop(call_sid, None)
        if _CONFIRMATION_PATTERN.search(speech):
            reply = await _finalize_booking(db, call_sid, turn_count, pending, language)
            history.append({"role": "assistant", "content": reply})
            return reply, False

    try:
        context = _retrieve_context(db, _anchor_query_for_retrieval(speech))
        messages = [{"role": "system", "content": _build_system_prompt(context, language)}, *history]

        # Python note for a reader new to Python coming from TS/Angular:
        # this loop's `else` clause (way below, at the same indent as
        # `for`) only runs if the loop finishes all its iterations WITHOUT
        # hitting `break` -- there's no equivalent in JS/TS `for`. Here
        # that means "the model still wanted another tool call when we ran
        # out of rounds," which falls through to the fallback line instead
        # of looping forever.
        for _ in range(_MAX_TOOL_ROUNDS + 1):
            result = await _llm_client.chat(
                messages,
                tools=_VOICE_TOOLS,
                tool_choice="auto",
                # LLMClient's own default (512) is too tight here -- confirmed
                # live: a real reply came back as pages of garbled whitespace/
                # ellipsis characters, the same "reasoning model spent its
                # budget before finishing" failure mode _parse_request in
                # booking_service.py already needed a raised budget for, just
                # silent instead of raising (this isn't json_mode, so nothing
                # validates the shape of what comes back). The final spoken
                # reply itself stays short (the system prompt already asks for
                # 1-3 sentences) -- this headroom is for the model's own
                # internal reasoning plus a whole tool-result history, not the
                # visible output.
                max_tokens=2048,
            )
            if not result.tool_calls:
                break
            messages.append(
                {
                    "role": "assistant",
                    "content": result.text,
                    "tool_calls": [
                        {
                            "id": tool_call.id,
                            "type": "function",
                            "function": {"name": tool_call.name, "arguments": tool_call.arguments},
                        }
                        for tool_call in result.tool_calls
                    ],
                }
            )
            for tool_call in result.tool_calls:
                tool_output = await _execute_tool(db, call_sid, turn_count, speech, tool_call, language)
                messages.append({"role": "tool", "tool_call_id": tool_call.id, "content": tool_output})
                # propose_booking's result is spoken verbatim, never handed
                # back to the model for another round -- see _execute_tool's
                # own comment on why paraphrasing it would undo the point
                # of the explicit "is that correct?" question.
                if tool_call.name == "propose_booking":
                    try:
                        parsed = json.loads(tool_output)
                    except json.JSONDecodeError:
                        parsed = {}
                    if parsed.get("status") == "awaiting_confirmation":
                        reply = parsed["say"]
                        history.append({"role": "assistant", "content": reply})
                        return reply, False
        else:
            return (_TOOL_LOOP_FALLBACK_NO if language == "no" else _TOOL_LOOP_FALLBACK), False
    except Exception:
        # Never leave the caller in dead air if the LLM call fails/times
        # out mid-call (see this agent's CLAUDE.md testing checklist) --
        # apologize and keep the call alive rather than hanging up on them.
        return (_LLM_ERROR_FALLBACK_NO if language == "no" else _LLM_ERROR_FALLBACK), False

    history.append({"role": "assistant", "content": result.text})
    return result.text, False


def _start_call(call_sid: str) -> str:
    """Resets this call's history and returns the greeting -- shared by
    /incoming (Twilio) and /dev/start (browser mic test page). Does NOT
    clear _call_caller_number -- voice_incoming sets that from the same
    request's own From field right after calling this, and /dev/start (the
    browser mic harness) has no real caller number to set in the first
    place."""
    _evict_stale_calls()
    _touch_call(call_sid)
    _call_history[call_sid] = []
    _call_silence_counts.pop(call_sid, None)
    _call_turn_counts.pop(call_sid, None)
    _call_language.pop(call_sid, None)
    _call_pending_slots.pop(call_sid, None)
    _call_pending_meeting_type.pop(call_sid, None)
    _call_pending_confirmation.pop(call_sid, None)
    return _GREETING


# Twilio's own BCP-47 codes for its speech recognition (<Gather>) and
# built-in TTS (<Say>) -- both support "nb-NO" (Norwegian Bokmål) directly,
# so switching is a language-code change, not a different API/provider.
def _twilio_lang_code(language: str) -> str:
    return "nb-NO" if language == "no" else "en-US"


def _gather(response: VoiceResponse, language: str = "en") -> None:
    """Appends a <Gather> that listens for speech and posts it to /gather.
    Shared by /incoming (start of call) and /gather (continuing the loop)
    so the listening behavior can't drift between the two call sites.

    `hints` biases Twilio's speech recognition toward these phrases without
    forbidding anything else -- doesn't fix every mishearing of "Mielikkix"
    (see the system prompt's own handling of that), but reduces how often
    it happens in the first place on a real call. Kept English-only even
    for a Norwegian-language Gather -- "Mielikkix" and "booking" are the
    same invented/loan words either way, and Twilio's `hints` don't take a
    per-language list.

    `language` selects Twilio's actual recognition language for this
    listen -- see _call_language/the language-latch comment in
    _handle_turn for how it's chosen.
    """
    gather = Gather(
        input="speech",
        action="/api/agents/voice/gather",
        method="POST",
        speech_timeout="auto",
        language=_twilio_lang_code(language),
        hints="Mielikkix, voice receptionist, booking, pricing",
    )
    response.append(gather)


@router.post("/incoming")
async def voice_incoming(request: Request):
    """Twilio calls this the instant someone dials the number. Greets the
    caller, then starts listening -- see this agent's CLAUDE.md,
    "How a Twilio voice call actually works", for the full webhook flow."""
    form = dict(await request.form())
    _assert_valid_twilio_request(request, form)

    call_sid = form.get("CallSid", "")
    # Twilio's own caller-ID field -- captured once, here, never from
    # speech-to-text, so propose_booking/_finalize_booking has a verified
    # phone number to fall back on if the caller doesn't state one.
    _call_caller_number[call_sid] = form.get("From", "")

    response = VoiceResponse()
    # New call: language always starts English (see _handle_turn's latch
    # comment -- there's no way to know yet), so the greeting and the very
    # first <Gather> both use the English Twilio voice/recognition.
    response.say(_start_call(call_sid), language=_twilio_lang_code("en"))
    _gather(response, "en")
    return Response(content=str(response), media_type="application/xml")


@router.post("/gather")
async def voice_gather(request: Request, db: Session = Depends(get_db)):
    """Twilio calls this after <Gather> captures speech (or after it times
    out with none). Generates a reply via agent-core's LLM client and loops
    back into another <Gather> to keep the conversation going.

    Python note: `.get(...)` with a default, not `[...]`, for every field
    read from `form` below -- Twilio's POST body is plain form data with no
    schema Python enforces, unlike a Pydantic request model elsewhere in
    this codebase, so a caller who said nothing (no SpeechResult) must not
    raise a KeyError and crash the call.
    """
    form = dict(await request.form())
    _assert_valid_twilio_request(request, form)

    call_sid = form.get("CallSid", "")
    reply, ended = await _handle_turn(db, call_sid, form.get("SpeechResult", ""))
    # Read AFTER _handle_turn -- it's the one that may have just latched
    # this call onto Norwegian for this very turn's reply.
    language = _call_language.get(call_sid, "en")

    response = VoiceResponse()
    response.say(reply, language=_twilio_lang_code(language))
    if ended:
        response.hangup()
    else:
        _gather(response, language)
    return Response(content=str(response), media_type="application/xml")


# ---------------------------------------------------------------------------
# Browser mic/speaker harness -- NOT part of the real Twilio call flow, never
# called by Twilio. Lets you talk to the same conversation logic above using
# your own microphone/speakers via the browser's built-in Web Speech API
# (free, no account, no Twilio) instead of a real phone call -- see
# apps/agents/voice-receptionist/CLAUDE.md for why a real call is currently
# blocked. Returns plain JSON, not TwiML, since a browser page has no use
# for Twilio's XML dialect.
#
# Two different audiences, two different gates:
#   - /dev/voice-test (the internal HTML page) is always debug-only -- it's
#     a raw test harness, not something to show a visitor.
#   - /dev/start and /dev/gather (the JSON API) additionally open up under
#     voice_agent_public_demo -- these are what website/'s polished
#     /demo/voice-receptionist page calls, so THAT page can be public while
#     the internal harness stays internal.
# ---------------------------------------------------------------------------


def _require_debug() -> None:
    """Blocks /dev/voice-test (the internal HTML test harness) unless
    settings.debug is set -- deliberately NOT reused for /dev/start and
    /dev/gather below, which have their own, deployable-to-production gate
    (see _require_demo_access). 404, not 403 -- no hint to an outsider that
    this route exists at all."""
    if not settings.debug:
        raise HTTPException(status_code=404, detail="Not found")


def _require_demo_access() -> None:
    """Blocks /dev/start and /dev/gather unless either debug mode or the
    dedicated public-demo flag is on (see config.py's voice_agent_public_demo
    for why this can't just reuse settings.debug). Without this, these
    routes are an unauthenticated, unlimited-by-anything-but-per-IP-rate-
    limit free proxy to the LLM (real Groq cost per call) reachable by
    anyone who finds the URL. 404, not 403 -- no hint to an outsider that
    these routes exist at all when neither is on."""
    if not (settings.debug or settings.voice_agent_public_demo):
        raise HTTPException(status_code=404, detail="Not found")


# Twilio CallSids are always "CA" + 32 lowercase hex chars. Real
# /incoming and /gather traffic writes into the exact same
# _call_history/_call_silence_counts/_call_turn_counts dicts these /dev/*
# routes do, keyed only by call_sid -- once voice_agent_public_demo is on
# for real strangers (not just you locally), a caller-supplied call_sid in
# that exact shape could otherwise let someone inject turns into a real
# live call if its CallSid ever leaked. Both real demo frontends generate
# call_sid via crypto.randomUUID() already (never this shape), so this is
# defense-in-depth, not something a legitimate demo caller should ever hit.
_TWILIO_CALL_SID_PATTERN = re.compile(r"^CA[0-9a-f]{32}$", re.IGNORECASE)


def _reject_twilio_shaped_call_sid(call_sid: str) -> None:
    if _TWILIO_CALL_SID_PATTERN.match(call_sid):
        raise HTTPException(status_code=400, detail="Invalid call_sid")


class _DevStartRequest(BaseModel):
    call_sid: str


class _DevTurnRequest(BaseModel):
    call_sid: str
    speech: str


class _DevReply(BaseModel):
    reply: str
    ended: bool = False
    # Best-effort corrected version of what the caller said, for the
    # browser demo's transcript UI to show instead of the raw mishearing --
    # None means no known correction, so the frontend just shows the raw
    # transcript. See _display_correction's docstring for why this is
    # deliberately decoupled from whether the agent actually understood
    # the question (it always does, via _anchor_query_for_retrieval).
    heard_as: str | None = None
    # "en" or "no" -- this call's CURRENT language after this turn (see
    # _call_language/_handle_turn's language-latch). The browser demo has
    # no Twilio Gather/Say to configure server-side, so it reads this back
    # to switch its own Web Speech API recognizer.lang and pick a Norwegian
    # voice for speechSynthesis once this flips to "no".
    language: str = "en"


@router.post("/dev/start", response_model=_DevReply, dependencies=[Depends(_require_demo_access)])
@limiter.limit("20/minute")
async def dev_voice_start(request: Request, body: _DevStartRequest):
    _reject_twilio_shaped_call_sid(body.call_sid)
    return _DevReply(reply=_start_call(body.call_sid))


@router.post("/dev/gather", response_model=_DevReply, dependencies=[Depends(_require_demo_access)])
@limiter.limit("15/minute")
async def dev_voice_gather(request: Request, body: _DevTurnRequest, db: Session = Depends(get_db)):
    # Each call here is a real Groq API call (a real cost) -- rate-limited
    # for the same reason /api/chat/message is (see that route): nothing
    # should be able to run up the LLM bill for free just by finding this
    # URL, whether that's "found" by an outsider (debug mode) or "used as
    # intended" by a public demo visitor (voice_agent_public_demo mode).
    _reject_twilio_shaped_call_sid(body.call_sid)
    reply, ended = await _handle_turn(db, body.call_sid, body.speech)
    language = _call_language.get(body.call_sid, "en")
    return _DevReply(reply=reply, ended=ended, heard_as=_display_correction(body.speech), language=language)


_DEV_VOICE_TEST_HTML_PATH = Path(__file__).resolve().parent.parent / "dev_tools" / "voice_test.html"


@router.get("/dev/voice-test", response_class=HTMLResponse, dependencies=[Depends(_require_debug)])
async def dev_voice_test_page():
    return HTMLResponse(content=_DEV_VOICE_TEST_HTML_PATH.read_text(encoding="utf-8"))
