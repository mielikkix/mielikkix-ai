"""
Voice Receptionist -- Phase 0 + Phase 1 (see
apps/agents/voice-receptionist/CLAUDE.md for the full phased plan).

Phase 0 proved the Twilio webhook round-trip works. Phase 1 adds the actual
conversation: greet the caller, listen, generate a reply via agent-core's
LLM client, and loop -- "just a friendly echo/conversation," deliberately
no intent routing or business-data grounding yet (that's Phase 2+).

WHY THIS FILE LIVES IN apps/api, NOT apps/agents/voice-receptionist:
see the module docstring history in git -- unchanged from Phase 0: Twilio
needs one running HTTP server, and apps/api is the "shared modular agent
process" apps/agents/CLAUDE.md describes.
"""

import re
import time
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import HTMLResponse, Response
from pydantic import BaseModel
from sqlalchemy.orm import Session
from twilio.request_validator import RequestValidator
from twilio.twiml.voice_response import VoiceResponse, Gather

from mielikkix_agent_core import LLMClient

from ..core.config import settings
from ..core.database import get_db
from ..core.limiter import limiter
from ..rag.embeddings import embed_query
from ..rag.pipeline import retrieve_chunks, retrieve_faqs, retrieve_products

router = APIRouter(prefix="/api/agents/voice", tags=["voice-receptionist"])

_GREETING = "Hello, thanks for calling Mielikkix. How can I help you today?"
_CLOSING_LINE = "Thanks for calling Mielikkix. Have a great day, goodbye!"
_SILENCE_CLOSING_LINE = "I haven't heard anything for a bit, so I'll let you go -- feel free to call back anytime. Goodbye!"
_TURN_CAP_CLOSING_LINE = "We've covered a lot today -- I'll have someone from the team follow up on anything else. Thanks for calling Mielikkix, goodbye!"

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

# Simple heuristic, not full intent classification (that's Phase 2+ per
# this agent's CLAUDE.md) -- just enough to let a caller end the call by
# saying so, instead of the loop continuing until they hang up the phone
# themselves or (in the browser demo) click Hang Up. Word-boundary matched
# for the same reason rag/pipeline.py's _matches_any is: a plain substring
# check on "bye" would misfire on "goodbye" being fine but also on
# unrelated words containing "bye"-like fragments in a longer sentence.
_GOODBYE_PATTERN = re.compile(
    r"\b(bye|goodbye|good bye|that'?s all|nothing else|no thanks|no that'?s it|"
    r"hang up|end the call|that'?s it for now)\b",
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


def _build_system_prompt(context: str) -> str:
    if context:
        return (
            f"{_SYSTEM_PROMPT_BASE}\n\nUse the following real information about "
            f"Mielikkix to answer the caller's question. If the answer isn't in "
            f"this information, say so plainly and offer to have someone follow "
            f"up, rather than guessing or inventing details.\n\n{context}"
        )
    return (
        f"{_SYSTEM_PROMPT_BASE} You don't currently have access to specific "
        f"business information for this question, so say so plainly and offer "
        f"to have someone follow up, rather than guessing."
    )

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


def _touch_call(call_sid: str) -> None:
    _call_last_seen[call_sid] = time.monotonic()


def _forget_call(call_sid: str) -> None:
    _call_last_seen.pop(call_sid, None)
    _call_history.pop(call_sid, None)
    _call_silence_counts.pop(call_sid, None)
    _call_turn_counts.pop(call_sid, None)


def _evict_stale_calls() -> None:
    cutoff = time.monotonic() - _CALL_STATE_TTL_SECONDS
    stale = [sid for sid, last_seen in _call_last_seen.items() if last_seen < cutoff]
    for sid in stale:
        _forget_call(sid)


_llm_client = LLMClient()


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
    """Core Phase 1+2 conversation turn: given what the caller said, returns
    (what the receptionist should say back, whether the call should end
    after saying it). Shared by the real Twilio-facing /gather route below
    AND the local-only /dev/gather route (browser mic test page) further
    down -- the actual conversation logic exists in exactly one place, and
    both interfaces just format its result differently (TwiML XML with a
    <Hangup/>, vs. plain JSON with an `ended` flag).
    """
    _evict_stale_calls()
    _touch_call(call_sid)

    speech = speech.strip()
    history = _call_history.setdefault(call_sid, [])

    if not speech:
        silence_count = _call_silence_counts.get(call_sid, 0) + 1
        _call_silence_counts[call_sid] = silence_count
        if silence_count >= _MAX_CONSECUTIVE_SILENCES:
            _forget_call(call_sid)
            return _SILENCE_CLOSING_LINE, True
        return "Sorry, I didn't catch that. Could you say that again?", False

    _call_silence_counts[call_sid] = 0  # any real speech resets the count

    if _GOODBYE_PATTERN.search(speech):
        _forget_call(call_sid)
        return _CLOSING_LINE, True

    turn_count = _call_turn_counts.get(call_sid, 0) + 1
    _call_turn_counts[call_sid] = turn_count
    if turn_count > _MAX_TURNS_PER_CALL:
        _forget_call(call_sid)
        return _TURN_CAP_CLOSING_LINE, True

    history.append({"role": "user", "content": speech})

    try:
        context = _retrieve_context(db, _anchor_query_for_retrieval(speech))
        result = await _llm_client.chat(
            [{"role": "system", "content": _build_system_prompt(context)}, *history]
        )
    except Exception:
        # Never leave the caller in dead air if the LLM call fails/times
        # out mid-call (see this agent's CLAUDE.md testing checklist) --
        # apologize and keep the call alive rather than hanging up on them.
        return "Sorry, I'm having trouble understanding right now. Could you try again in a moment?", False

    history.append({"role": "assistant", "content": result.text})
    return result.text, False


def _start_call(call_sid: str) -> str:
    """Resets this call's history and returns the greeting -- shared by
    /incoming (Twilio) and /dev/start (browser mic test page)."""
    _evict_stale_calls()
    _touch_call(call_sid)
    _call_history[call_sid] = []
    _call_silence_counts.pop(call_sid, None)
    _call_turn_counts.pop(call_sid, None)
    return _GREETING


def _gather(response: VoiceResponse) -> None:
    """Appends a <Gather> that listens for speech and posts it to /gather.
    Shared by /incoming (start of call) and /gather (continuing the loop)
    so the listening behavior can't drift between the two call sites.

    `hints` biases Twilio's speech recognition toward these phrases without
    forbidding anything else -- doesn't fix every mishearing of "Mielikkix"
    (see the system prompt's own handling of that), but reduces how often
    it happens in the first place on a real call.
    """
    gather = Gather(
        input="speech",
        action="/api/agents/voice/gather",
        method="POST",
        speech_timeout="auto",
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

    response = VoiceResponse()
    response.say(_start_call(form.get("CallSid", "")))
    _gather(response)
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

    reply, ended = await _handle_turn(db, form.get("CallSid", ""), form.get("SpeechResult", ""))

    response = VoiceResponse()
    response.say(reply)
    if ended:
        response.hangup()
    else:
        _gather(response)
    return Response(content=str(response), media_type="application/xml")


# ---------------------------------------------------------------------------
# Local browser mic/speaker test harness -- NOT part of the real Twilio call
# flow, never called by Twilio. Lets you talk to the same conversation logic
# above using your own microphone/speakers via the browser's built-in Web
# Speech API (free, no account, no Twilio) instead of a real phone call --
# see apps/agents/voice-receptionist/CLAUDE.md for why a real call is
# currently blocked. Returns plain JSON, not TwiML, since a browser page has
# no use for Twilio's XML dialect.
# ---------------------------------------------------------------------------


def _require_debug() -> None:
    """Blocks all /dev/* routes unless settings.debug is set. Without this,
    these routes are an unauthenticated, unlimited-by-anything-but-per-IP-
    rate-limit free proxy to the LLM (real Groq cost per call) reachable by
    anyone who finds the URL -- and /dev/gather writes into the exact same
    _call_history/_call_silence_counts dicts a real Twilio call uses, keyed
    only by a caller-supplied call_sid string, so it's also a way to inject
    turns into a live call if its CallSid ever leaked. 404, not 403 --
    no hint to an outsider that these routes exist at all."""
    if not settings.debug:
        raise HTTPException(status_code=404, detail="Not found")


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


@router.post("/dev/start", response_model=_DevReply, dependencies=[Depends(_require_debug)])
@limiter.limit("20/minute")
async def dev_voice_start(request: Request, body: _DevStartRequest):
    return _DevReply(reply=_start_call(body.call_sid))


@router.post("/dev/gather", response_model=_DevReply, dependencies=[Depends(_require_debug)])
@limiter.limit("15/minute")
async def dev_voice_gather(request: Request, body: _DevTurnRequest, db: Session = Depends(get_db)):
    # Each call here is a real Groq API call (a real cost) once this page's
    # link leaves your own machine -- rate-limited for the same reason
    # /api/chat/message is (see that route): nothing should be able to run
    # up the LLM bill for free just by finding this URL.
    reply, ended = await _handle_turn(db, body.call_sid, body.speech)
    return _DevReply(reply=reply, ended=ended, heard_as=_display_correction(body.speech))


_DEV_VOICE_TEST_HTML_PATH = Path(__file__).resolve().parent.parent / "dev_tools" / "voice_test.html"


@router.get("/dev/voice-test", response_class=HTMLResponse, dependencies=[Depends(_require_debug)])
async def dev_voice_test_page():
    return HTMLResponse(content=_DEV_VOICE_TEST_HTML_PATH.read_text(encoding="utf-8"))
