"""
Tests for the Voice Receptionist webhook (see
apps/agents/voice-receptionist/CLAUDE.md) -- Phase 0 (signature validation),
Phase 1 (the LLM-backed conversation loop), and Phase 2 (RAG grounding via
_retrieve_context). Uses a plain TestClient against the same `app` object
everything else imports, not the `client`/`db_session` fixtures from
conftest.py -- routes still get a real `db` session (via FastAPI's normal
dependency injection against whatever DATABASE_URL is configured), but
_retrieve_context itself is always mocked here, so no test actually queries
the database or loads the real embedding model. The LLM client is always
mocked too; no test in this file makes a real Groq call.
"""

import json
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock

import pytest
from fastapi.testclient import TestClient
from twilio.request_validator import RequestValidator

from app.main import app
from app.core.config import settings
from app.api import agents_voice
from app.services import booking_service, support_service
from mielikkix_agent_core import LLMResult, LLMUsage, ToolCall

client = TestClient(app)


@pytest.fixture(autouse=True)
def _debug_mode(monkeypatch):
    """All /dev/* routes 404 outside settings.debug (see agents_voice.py's
    _require_debug) -- this module's whole point is exercising those
    routes, so default every test in it to debug mode. The one test that
    cares about the opposite (production-mode 404) overrides this itself."""
    monkeypatch.setattr(settings, "debug", True)


def test_incoming_call_without_auth_token_configured(monkeypatch):
    """Dev-mode fallback: with no Twilio Auth Token set, signature
    validation is skipped and the endpoint still answers."""
    monkeypatch.setattr(settings, "twilio_auth_token", "")

    resp = client.post("/api/agents/voice/incoming", data={"CallSid": "CAtest123"})

    assert resp.status_code == 200
    assert resp.headers["content-type"].startswith("application/xml")
    assert "Gather" in resp.text
    assert agents_voice._GREETING in resp.text


def test_incoming_call_rejects_forged_request(monkeypatch):
    """Once an Auth Token is configured, a request without a valid
    X-Twilio-Signature header must be rejected -- this is the check that
    stops a stranger from posting fake call events (and running up the LLM
    bill) at this endpoint."""
    monkeypatch.setattr(settings, "twilio_auth_token", "test-auth-token")
    monkeypatch.setattr(settings, "voice_agent_public_base_url", "https://voice.example.com")

    resp = client.post(
        "/api/agents/voice/incoming",
        data={"CallSid": "CAtest123"},
        headers={"X-Twilio-Signature": "not-a-real-signature"},
    )

    assert resp.status_code == 403


def test_incoming_call_accepts_genuinely_signed_request(monkeypatch):
    """A request signed the way Twilio actually signs it (same algorithm,
    computed against the configured public base URL) must be accepted."""
    monkeypatch.setattr(settings, "twilio_auth_token", "test-auth-token")
    monkeypatch.setattr(settings, "voice_agent_public_base_url", "https://voice.example.com")

    form = {"CallSid": "CAtest123"}
    validator = RequestValidator("test-auth-token")
    signature = validator.compute_signature(
        "https://voice.example.com/api/agents/voice/incoming", form
    )

    resp = client.post(
        "/api/agents/voice/incoming",
        data=form,
        headers={"X-Twilio-Signature": signature},
    )

    assert resp.status_code == 200
    assert agents_voice._GREETING in resp.text


def test_gather_generates_reply_via_llm_and_loops(monkeypatch):
    monkeypatch.setattr(settings, "twilio_auth_token", "")
    monkeypatch.setattr(agents_voice, "_retrieve_context", lambda db, query, **kwargs: "")
    agents_voice._call_history.clear()
    fake_chat = AsyncMock(
        return_value=LLMResult(
            text="Sure, we're open 9 to 5 on weekdays.",
            usage=LLMUsage(prompt_tokens=20, completion_tokens=10, total_tokens=30),
        )
    )
    monkeypatch.setattr(agents_voice._llm_client, "chat", fake_chat)

    resp = client.post(
        "/api/agents/voice/gather",
        data={"CallSid": "CAtest123", "SpeechResult": "What are your hours?"},
    )

    assert resp.status_code == 200
    assert "we're open 9 to 5" in resp.text
    assert "Gather" in resp.text
    fake_chat.assert_awaited_once()
    # The system prompt plus this turn's user/assistant messages should now
    # be tracked so the next turn has conversational context.
    assert agents_voice._call_history["CAtest123"] == [
        {"role": "user", "content": "What are your hours?"},
        {"role": "assistant", "content": "Sure, we're open 9 to 5 on weekdays."},
    ]


def test_gather_reprompts_on_first_silence(monkeypatch):
    monkeypatch.setattr(settings, "twilio_auth_token", "")
    agents_voice._call_silence_counts.pop("CAtest456", None)
    fake_chat = AsyncMock()
    monkeypatch.setattr(agents_voice._llm_client, "chat", fake_chat)

    resp = client.post(
        "/api/agents/voice/gather",
        data={"CallSid": "CAtest456", "SpeechResult": ""},
    )

    assert resp.status_code == 200
    assert "didn't catch that" in resp.text
    assert "Gather" in resp.text
    assert "Hangup" not in resp.text
    fake_chat.assert_not_awaited()


def test_gather_ends_call_after_max_consecutive_silences(monkeypatch):
    """A caller who walked away without hanging up (or forgot to click Hang
    Up in the browser demo) shouldn't leave the call running forever --
    after _MAX_CONSECUTIVE_SILENCES silent turns in a row, the call ends
    itself with a closing line instead of re-prompting indefinitely."""
    monkeypatch.setattr(settings, "twilio_auth_token", "")
    call_sid = "CAtest-silence"
    agents_voice._call_silence_counts.pop(call_sid, None)
    fake_chat = AsyncMock()
    monkeypatch.setattr(agents_voice._llm_client, "chat", fake_chat)

    for _ in range(agents_voice._MAX_CONSECUTIVE_SILENCES - 1):
        resp = client.post("/api/agents/voice/gather", data={"CallSid": call_sid, "SpeechResult": ""})
        assert "Gather" in resp.text
        assert "Hangup" not in resp.text

    final_resp = client.post("/api/agents/voice/gather", data={"CallSid": call_sid, "SpeechResult": ""})

    assert final_resp.status_code == 200
    assert "Hangup" in final_resp.text
    assert "Gather" not in final_resp.text
    assert agents_voice._SILENCE_CLOSING_LINE in final_resp.text
    fake_chat.assert_not_awaited()
    assert call_sid not in agents_voice._call_silence_counts


def test_gather_ends_call_on_goodbye_phrase(monkeypatch):
    monkeypatch.setattr(settings, "twilio_auth_token", "")
    fake_chat = AsyncMock()
    monkeypatch.setattr(agents_voice._llm_client, "chat", fake_chat)

    resp = client.post(
        "/api/agents/voice/gather",
        data={"CallSid": "CAtest-goodbye", "SpeechResult": "Okay, thanks, that's all, goodbye!"},
    )

    assert resp.status_code == 200
    assert agents_voice._CLOSING_LINE in resp.text
    assert "Hangup" in resp.text
    assert "Gather" not in resp.text
    fake_chat.assert_not_awaited()
    assert "CAtest-goodbye" not in agents_voice._call_history


def test_gather_ends_call_after_max_turns(monkeypatch):
    """A caller who just keeps talking (never says goodbye, never goes
    silent) must still be cut off eventually -- otherwise one open phone
    line can generate an unbounded number of paid Groq calls."""
    monkeypatch.setattr(settings, "twilio_auth_token", "")
    monkeypatch.setattr(agents_voice, "_retrieve_context", lambda db, query, **kwargs: "")
    call_sid = "CAtest-turncap"
    agents_voice._call_turn_counts.pop(call_sid, None)
    agents_voice._call_history.pop(call_sid, None)
    fake_chat = AsyncMock(return_value=LLMResult(text="Sure, here's more info.", usage=None))
    monkeypatch.setattr(agents_voice._llm_client, "chat", fake_chat)

    for _ in range(agents_voice._MAX_TURNS_PER_CALL):
        resp = client.post(
            "/api/agents/voice/gather", data={"CallSid": call_sid, "SpeechResult": "tell me more"}
        )
        assert "Hangup" not in resp.text

    final_resp = client.post(
        "/api/agents/voice/gather", data={"CallSid": call_sid, "SpeechResult": "tell me more"}
    )

    assert final_resp.status_code == 200
    assert "Hangup" in final_resp.text
    assert "Gather" not in final_resp.text
    assert agents_voice._TURN_CAP_CLOSING_LINE in final_resp.text
    assert call_sid not in agents_voice._call_turn_counts
    assert call_sid not in agents_voice._call_history


def test_gather_falls_back_gracefully_on_llm_error(monkeypatch):
    """Never leave the caller in dead air if the LLM call fails -- see this
    agent's CLAUDE.md testing checklist."""
    monkeypatch.setattr(settings, "twilio_auth_token", "")
    monkeypatch.setattr(agents_voice, "_retrieve_context", lambda db, query, **kwargs: "")
    fake_chat = AsyncMock(side_effect=RuntimeError("groq is down"))
    monkeypatch.setattr(agents_voice._llm_client, "chat", fake_chat)

    resp = client.post(
        "/api/agents/voice/gather",
        data={"CallSid": "CAtest789", "SpeechResult": "hello?"},
    )

    assert resp.status_code == 200
    assert "trouble understanding" in resp.text
    assert "Gather" in resp.text


# --- Local browser mic test harness (/dev/*) -- not part of the real
# Twilio call flow; see agents_voice.py's own comment above these routes. ---


def test_dev_start_returns_greeting_as_json():
    resp = client.post("/api/agents/voice/dev/start", json={"call_sid": "CAdevtest1"})

    assert resp.status_code == 200
    assert resp.json() == {"reply": agents_voice._GREETING, "ended": False, "heard_as": None, "language": "en"}


def test_dev_routes_404_outside_debug_mode(monkeypatch):
    """Outside debug mode (and with the public demo flag off), /dev/* must
    not exist -- not just reject with 403/401, so an outsider scanning for
    routes gets no hint they're there."""
    monkeypatch.setattr(settings, "debug", False)
    monkeypatch.setattr(settings, "voice_agent_public_demo", False)

    assert client.post("/api/agents/voice/dev/start", json={"call_sid": "not-twilio-shaped"}).status_code == 404
    assert client.post(
        "/api/agents/voice/dev/gather", json={"call_sid": "not-twilio-shaped", "speech": "hi"}
    ).status_code == 404
    assert client.get("/api/agents/voice/dev/voice-test").status_code == 404


def test_public_demo_flag_opens_json_routes_but_not_the_internal_harness(monkeypatch):
    """voice_agent_public_demo=True (independent of debug) must open
    /dev/start and /dev/gather for the public marketing-site demo page,
    while /dev/voice-test -- the internal HTML test harness, not meant for
    a visitor -- stays 404 unless debug is also on."""
    monkeypatch.setattr(settings, "debug", False)
    monkeypatch.setattr(settings, "voice_agent_public_demo", True)
    monkeypatch.setattr(agents_voice, "_retrieve_context", lambda db, query, **kwargs: "")

    start_resp = client.post("/api/agents/voice/dev/start", json={"call_sid": "public-demo-caller-1"})
    assert start_resp.status_code == 200

    fake_chat = AsyncMock(return_value=LLMResult(text="Sure thing.", usage=None))
    monkeypatch.setattr(agents_voice._llm_client, "chat", fake_chat)
    gather_resp = client.post(
        "/api/agents/voice/dev/gather",
        json={"call_sid": "public-demo-caller-1", "speech": "what do you do"},
    )
    assert gather_resp.status_code == 200

    assert client.get("/api/agents/voice/dev/voice-test").status_code == 404


def test_dev_routes_reject_twilio_shaped_call_sid(monkeypatch):
    """A call_sid in the exact shape Twilio issues real CallSids in ("CA" +
    32 hex chars) must be rejected on the /dev/* routes -- those routes
    write into the same call-state dicts the real Twilio flow uses, keyed
    only by call_sid, so accepting this shape here would let a public demo
    visitor collide with (or inject turns into) a real live call."""
    twilio_shaped = "CA" + "0" * 32

    assert client.post(
        "/api/agents/voice/dev/start", json={"call_sid": twilio_shaped}
    ).status_code == 400
    assert client.post(
        "/api/agents/voice/dev/gather", json={"call_sid": twilio_shaped, "speech": "hi"}
    ).status_code == 400


def test_dev_gather_uses_same_turn_logic_as_real_gather(monkeypatch):
    """The /dev/gather JSON route and the Twilio-facing /gather TwiML route
    must produce the same reply for the same input -- they share
    _handle_turn precisely so this can't drift."""
    monkeypatch.setattr(agents_voice, "_retrieve_context", lambda db, query, **kwargs: "")
    agents_voice._call_history.clear()
    fake_chat = AsyncMock(
        return_value=LLMResult(
            text="We're open every day 9 to 6.",
            usage=LLMUsage(prompt_tokens=15, completion_tokens=8, total_tokens=23),
        )
    )
    monkeypatch.setattr(agents_voice._llm_client, "chat", fake_chat)

    resp = client.post(
        "/api/agents/voice/dev/gather",
        json={"call_sid": "CAdevtest2", "speech": "What are your hours?"},
    )

    assert resp.status_code == 200
    assert resp.json() == {
        "reply": "We're open every day 9 to 6.",
        "ended": False,
        "heard_as": None,
        "language": "en",
    }


def test_display_correction_rewrites_known_mishearings():
    assert agents_voice._display_correction("what is Millie cakes") == "what is Mielikkix"
    assert agents_voice._display_correction("may I know about milk cakes") == "may I know about Mielikkix"
    assert agents_voice._display_correction("what is Mila cakes") == "what is Mielikkix"


def test_display_correction_returns_none_for_unrecognized_or_correct_text():
    # Not a known mishearing pattern -- nothing to correct, show as-is.
    assert agents_voice._display_correction("what are your hours") is None
    # Already says Mielikkix -- nothing to correct.
    assert agents_voice._display_correction("what is Mielikkix") is None


def test_dev_gather_returns_heard_as_for_known_mishearing(monkeypatch):
    monkeypatch.setattr(agents_voice, "_retrieve_context", lambda db, query, **kwargs: "")
    agents_voice._call_history.clear()
    fake_chat = AsyncMock(return_value=LLMResult(text="Mielikkix is an AI chat platform.", usage=None))
    monkeypatch.setattr(agents_voice._llm_client, "chat", fake_chat)

    resp = client.post(
        "/api/agents/voice/dev/gather",
        json={"call_sid": "CAdevtest-heardas", "speech": "what is Millie cakes"},
    )

    assert resp.status_code == 200
    assert resp.json()["heard_as"] == "what is Mielikkix"


def test_dev_gather_reports_ended_on_goodbye():
    resp = client.post(
        "/api/agents/voice/dev/gather",
        json={"call_sid": "CAdevtest-bye", "speech": "No that's everything, bye!"},
    )

    assert resp.status_code == 200
    body = resp.json()
    assert body["ended"] is True
    assert body["reply"] == agents_voice._CLOSING_LINE


# --- Phase 2: RAG grounding ---


def test_gather_grounds_system_prompt_in_retrieved_context(monkeypatch):
    """When _retrieve_context finds something relevant, it must actually
    reach the LLM call as part of the system prompt -- not just be computed
    and discarded."""
    monkeypatch.setattr(settings, "twilio_auth_token", "")
    monkeypatch.setattr(
        agents_voice,
        "_retrieve_context",
        lambda db, query, **kwargs: "Mielikkix offers a Voice Receptionist, Booking Assistant, and Support Triage agent.",
    )
    agents_voice._call_history.clear()
    fake_chat = AsyncMock(
        return_value=LLMResult(text="We offer three Force agents so far.", usage=None)
    )
    monkeypatch.setattr(agents_voice._llm_client, "chat", fake_chat)

    resp = client.post(
        "/api/agents/voice/gather",
        data={"CallSid": "CAtest999", "SpeechResult": "What agents do you offer?"},
    )

    assert resp.status_code == 200
    sent_messages = fake_chat.call_args.args[0]
    system_message = sent_messages[0]["content"]
    assert "Booking Assistant" in system_message
    assert "answer the caller's question" in system_message


def test_gather_falls_back_to_ungrounded_prompt_when_no_context_found(monkeypatch):
    """No business configured, or nothing scored above the confidence
    threshold -- either way _retrieve_context returns "", and the system
    prompt must fall back to the honest "I don't know" framing rather than
    silently including an empty context block."""
    monkeypatch.setattr(settings, "twilio_auth_token", "")
    monkeypatch.setattr(agents_voice, "_retrieve_context", lambda db, query, **kwargs: "")
    agents_voice._call_history.clear()
    fake_chat = AsyncMock(return_value=LLMResult(text="I'm not sure about that.", usage=None))
    monkeypatch.setattr(agents_voice._llm_client, "chat", fake_chat)

    resp = client.post(
        "/api/agents/voice/gather",
        data={"CallSid": "CAtest1000", "SpeechResult": "What's the meaning of life?"},
    )

    assert resp.status_code == 200
    system_message = fake_chat.call_args.args[0][0]["content"]
    assert "don't currently have access to specific business information" in system_message


def test_system_prompt_always_includes_mishearing_guidance(monkeypatch):
    """'Mielikkix' is an invented word, so speech-to-text (Twilio's, and the
    browser demo's) regularly mishears it as something else entirely (seen
    in practice: "Millie Cakes", "Millie kicks"). The system prompt must
    always tell the LLM to treat a garbled, similar-sounding company name
    as Mielikkix itself, not as some other unknown business."""
    monkeypatch.setattr(settings, "twilio_auth_token", "")
    monkeypatch.setattr(agents_voice, "_retrieve_context", lambda db, query, **kwargs: "")
    agents_voice._call_history.clear()
    fake_chat = AsyncMock(return_value=LLMResult(text="We're an AI agent platform.", usage=None))
    monkeypatch.setattr(agents_voice._llm_client, "chat", fake_chat)

    client.post(
        "/api/agents/voice/gather",
        data={"CallSid": "CAtest-mishearing", "SpeechResult": "What is Millie Cakes?"},
    )

    system_message = fake_chat.call_args.args[0][0]["content"]
    assert "phonetically similar" in system_message
    assert "Millie Cakes" in system_message


def test_anchor_query_for_retrieval_handles_unenumerated_mishearings():
    """The fix is general (recognizing the *shape* of an identity
    question), not a growing list of specific mishearings -- this covers
    "milky cakes", a mishearing that came up in real testing after the
    first (list-based) version of this fix already shipped, proving the
    general version doesn't need a new list entry for it."""
    assert agents_voice._anchor_query_for_retrieval("what is milky cakes") == "Mielikkix what is milky cakes"
    assert (
        agents_voice._anchor_query_for_retrieval("what services provided by Millie kicks")
        == "Mielikkix what services provided by Millie kicks"
    )
    assert agents_voice._anchor_query_for_retrieval("tell me about melee cakes") == "Mielikkix tell me about melee cakes"


def test_anchor_query_for_retrieval_handles_know_about_phrasing():
    """"tell me about" was covered but "know about" / "would like to know
    about" wasn't -- both real phrasings that came up in testing and fell
    through to an unanchored (and therefore failing) query."""
    assert agents_voice._anchor_query_for_retrieval("know about milky cakes") == "Mielikkix know about milky cakes"
    assert (
        agents_voice._anchor_query_for_retrieval("pratibha I would like to know about Millie kicks")
        == "Mielikkix pratibha I would like to know about Millie kicks"
    )


def test_anchor_query_for_retrieval_only_skips_when_already_named(monkeypatch):
    """No shape-matching anymore (see the long comment above
    _anchor_query_for_retrieval for why: question-shape detection kept
    missing real phrasing, and broke entirely when speech recognition
    clipped the question words off). ANY speech not already naming
    Mielikkix gets it anchored on -- including a bare fragment with no
    recognizable question shape at all, e.g. "mini cakes" alone (a real
    case from testing where "what is" was clipped off before this
    function ever saw the text)."""
    assert agents_voice._anchor_query_for_retrieval("mini cakes") == "Mielikkix mini cakes"
    assert agents_voice._anchor_query_for_retrieval("how are you today") == "Mielikkix how are you today"
    # Already says "Mielikkix" -- don't double up.
    assert agents_voice._anchor_query_for_retrieval("what is Mielikkix's pricing") == "what is Mielikkix's pricing"
    assert agents_voice._anchor_query_for_retrieval("is Mielikkix") == "is Mielikkix"


def test_retrieve_context_has_no_relevance_gate_only_a_noise_floor(monkeypatch):
    """Real finding from testing: once a query is anchored with
    "Mielikkix", every candidate scores in roughly the same range
    regardless of actual relevance (measured: "Mielikkix tell me a joke"
    scored 0.32, "Mielikkix mini cakes" scored 0.25) -- there's no
    meaningful score gap left to set a relevance threshold on. So
    _retrieve_context no longer tries to judge relevance by score at all;
    it only drops literal noise (_RAG_MINIMUM_SCORE) and hands the LLM
    whatever real content comes back, trusting the system prompt's own
    "use this if it helps, say so plainly if it doesn't" instruction."""
    fake_match = [
        ("Mielikkix Features page content...", 0.229),  # would've failed the old 0.25 threshold
        ("Noise below the floor", 0.02),
    ]
    monkeypatch.setattr(settings, "voice_agent_business_id", "test-business-id")
    monkeypatch.setattr(agents_voice, "embed_query", lambda q: [0.1, 0.2])
    monkeypatch.setattr(agents_voice, "retrieve_chunks", lambda *a, **k: fake_match)
    monkeypatch.setattr(agents_voice, "retrieve_faqs", lambda *a, **k: [])
    monkeypatch.setattr(agents_voice, "retrieve_products", lambda *a, **k: [])

    context = agents_voice._retrieve_context(None, "Mielikkix anything")

    assert "Mielikkix Features page content..." in context
    assert "Noise below the floor" not in context


def test_gather_finds_real_content_for_a_mishearing_not_in_any_hardcoded_list(monkeypatch):
    """End-to-end proof that "milky cakes" (never explicitly listed
    anywhere in this codebase) still reaches _retrieve_context as an
    anchored, findable query."""
    monkeypatch.setattr(settings, "twilio_auth_token", "")
    agents_voice._call_history.clear()
    captured_queries = []

    def fake_retrieve_context(db, query, **kwargs):
        captured_queries.append(query)
        return "Mielikkix is an AI chat platform for small businesses."

    monkeypatch.setattr(agents_voice, "_retrieve_context", fake_retrieve_context)
    fake_chat = AsyncMock(return_value=LLMResult(text="Mielikkix is an AI chat platform.", usage=None))
    monkeypatch.setattr(agents_voice._llm_client, "chat", fake_chat)

    client.post(
        "/api/agents/voice/gather",
        data={"CallSid": "CAtest-milky", "SpeechResult": "may I know what is milky cakes"},
    )

    assert captured_queries == ["Mielikkix may I know what is milky cakes"]


def test_gather_biases_twilio_speech_recognition_with_hints(monkeypatch):
    """Reduces how often Twilio mishears "Mielikkix" in the first place on
    a real call (the system prompt above handles it when it happens
    anyway, but avoiding it is better than correcting it)."""
    monkeypatch.setattr(settings, "twilio_auth_token", "")

    resp = client.post("/api/agents/voice/incoming", data={"CallSid": "CAtest-hints"})

    assert 'hints="Mielikkix' in resp.text


def test_dev_voice_test_page_serves_html():
    resp = client.get("/api/agents/voice/dev/voice-test")

    assert resp.status_code == 200
    assert resp.headers["content-type"].startswith("text/html")
    assert "SpeechRecognition" in resp.text


# ---------------------------------------------------------------------------
# Phase 4: agent-to-agent handoff -- the LLM can now call check_availability/
# propose_booking mid-call (see agents_voice.py's _VOICE_TOOLS, _execute_tool,
# and the tool-calling loop in _handle_turn). propose_booking/_finalize_booking
# are a deliberate two-turn split: propose_booking stages a confirmation and
# speaks a server-generated (spelled-out-email) readback verbatim, never
# handed back to the LLM to paraphrase; only the caller's own next-turn "yes"
# (checked via _CONFIRMATION_PATTERN against raw speech, not another LLM tool
# call) triggers _finalize_booking, which books using exactly what was
# already read back -- see agents_voice.py's own comments on why (a misheard
# email is only catchable if the readback is guaranteed verbatim). Both
# booking_service functions are always mocked here, same "never a real
# Google Calendar/LLM call" convention as the rest of this file -- and
# specifically to avoid this file's plain module-level TestClient (no
# db_session fixture, no dependency override) writing a real Booking row
# against whatever DATABASE_URL happens to be configured.
# ---------------------------------------------------------------------------


def _tool_call_result(text: str, *tool_calls: ToolCall) -> LLMResult:
    return LLMResult(text=text, usage=None, tool_calls=list(tool_calls) or None)


def test_gather_check_availability_tool_populates_pending_slots(monkeypatch):
    monkeypatch.setattr(settings, "twilio_auth_token", "")
    monkeypatch.setattr(agents_voice, "_retrieve_context", lambda db, query, **kwargs: "")
    call_sid = "CAtest-checkavail"
    agents_voice._forget_call(call_sid)

    monday = datetime.now(timezone.utc) + timedelta(days=(7 - datetime.now(timezone.utc).weekday()))
    slots = [
        booking_service.SlotOption(start=monday.replace(hour=14, minute=0), end=monday.replace(hour=14, minute=30)),
        booking_service.SlotOption(start=monday.replace(hour=16, minute=0), end=monday.replace(hour=16, minute=30)),
    ]
    fake_resolve = AsyncMock(
        return_value=booking_service.ResolveBookingResult(
            status="needs_selection", slots=slots, meeting_type="consultation", duration_minutes=30
        )
    )
    monkeypatch.setattr(booking_service, "resolve_booking_request", fake_resolve)

    tool_call = ToolCall(id="call_1", name="check_availability", arguments='{"description": "a consultation"}')
    fake_chat = AsyncMock(
        side_effect=[
            _tool_call_result("", tool_call),
            _tool_call_result("I've got two times open -- does either work for you?"),
        ]
    )
    monkeypatch.setattr(agents_voice._llm_client, "chat", fake_chat)

    resp = client.post(
        "/api/agents/voice/gather",
        data={"CallSid": call_sid, "SpeechResult": "I'd like to book a consultation"},
    )

    assert resp.status_code == 200
    assert "does either work for you" in resp.text
    fake_resolve.assert_awaited_once()
    assert agents_voice._call_pending_slots[call_sid] == slots
    assert agents_voice._call_pending_meeting_type[call_sid] == "consultation"


def test_check_availability_truncates_slots_before_storing_or_returning_them(monkeypatch):
    """Real live bug: resolve_booking_request can return up to 8 slots, but
    only _MAX_SPOKEN_SLOTS are ever meant to be offered -- when all 8 were
    included in the tool result, the model's own spoken "1, 2" labels
    didn't reliably line up with their real index in the full list, so
    propose_booking(index=1) could silently stage a slot the caller never
    actually heard or agreed to. Truncating BEFORE storing (not just
    trusting the model to only mention a few) makes that mismatch
    impossible -- index 1 in what's returned and index 1 in
    _call_pending_slots must always be the exact same slot."""
    monkeypatch.setattr(settings, "twilio_auth_token", "")
    monkeypatch.setattr(agents_voice, "_retrieve_context", lambda db, query, **kwargs: "")
    call_sid = "CAtest-truncate"
    agents_voice._forget_call(call_sid)

    monday = datetime.now(timezone.utc) + timedelta(days=(7 - datetime.now(timezone.utc).weekday()))
    many_slots = [
        booking_service.SlotOption(start=monday.replace(hour=9 + i, minute=0), end=monday.replace(hour=9 + i, minute=30))
        for i in range(8)
    ]
    monkeypatch.setattr(
        booking_service,
        "resolve_booking_request",
        AsyncMock(
            return_value=booking_service.ResolveBookingResult(
                status="needs_selection", slots=many_slots, meeting_type="call", duration_minutes=30
            )
        ),
    )
    tool_call = ToolCall(id="call_1", name="check_availability", arguments='{"description": "a call"}')
    fake_chat = AsyncMock(
        side_effect=[
            _tool_call_result("", tool_call),
            _tool_call_result("A couple of times are open -- which works?"),
        ]
    )
    monkeypatch.setattr(agents_voice._llm_client, "chat", fake_chat)

    client.post(
        "/api/agents/voice/gather",
        data={"CallSid": call_sid, "SpeechResult": "book me a call"},
    )

    assert agents_voice._call_pending_slots[call_sid] == many_slots[: agents_voice._MAX_SPOKEN_SLOTS]
    # The tool-result JSON fed back to the LLM must only ever contain the
    # same truncated set -- never all 8.
    tool_result = json.loads(fake_chat.call_args_list[1].args[0][-1]["content"])
    assert len(tool_result["slots"]) == agents_voice._MAX_SPOKEN_SLOTS


def test_gather_propose_booking_speaks_deterministic_readback_without_booking_yet(monkeypatch):
    """propose_booking must never book on its own -- it only stages
    _call_pending_confirmation and speaks a server-generated readback
    (reading the email back and explicitly asking if it's correct)
    verbatim, without a second LLM call to paraphrase it. Only the
    caller's OWN next-turn "yes" (a separate test) actually books."""
    monkeypatch.setattr(settings, "twilio_auth_token", "")
    monkeypatch.setattr(agents_voice, "_retrieve_context", lambda db, query, **kwargs: "")
    call_sid = "CAtest-propose"
    agents_voice._forget_call(call_sid)

    monday = datetime.now(timezone.utc) + timedelta(days=(7 - datetime.now(timezone.utc).weekday()))
    slots = [booking_service.SlotOption(start=monday.replace(hour=14, minute=0), end=monday.replace(hour=14, minute=30))]
    agents_voice._call_pending_slots[call_sid] = slots
    fake_confirm = AsyncMock()
    monkeypatch.setattr(booking_service, "confirm_booking_slot", fake_confirm)

    propose_call = ToolCall(
        id="call_1",
        name="propose_booking",
        arguments='{"slot_index": 1, "name": "John", "email": "johnjobs10@example.com"}',
    )
    # Only ONE LLMResult queued -- propose_booking short-circuits the turn
    # before a second LLM call would ever happen (see the assert on
    # fake_chat.await_count below).
    fake_chat = AsyncMock(side_effect=[_tool_call_result("", propose_call)])
    monkeypatch.setattr(agents_voice._llm_client, "chat", fake_chat)

    resp = client.post(
        "/api/agents/voice/gather",
        data={"CallSid": call_sid, "SpeechResult": "here is my name John and email john jobs 10 at example dot com"},
    )

    assert resp.status_code == 200
    assert "Shall I book it" in resp.text
    # The email is read back and explicitly checked, not silently trusted
    # -- this is the whole point of the deterministic readback.
    assert "johnjobs10@example.com" in resp.text
    assert "Is that correct" in resp.text
    fake_confirm.assert_not_awaited()
    fake_chat.assert_awaited_once()
    pending = agents_voice._call_pending_confirmation[call_sid]
    assert pending["slot_index"] == 1
    assert pending["name"] == "John"
    assert pending["email"] == "johnjobs10@example.com"


def test_gather_propose_booking_rejects_a_malformed_email_instead_of_staging_it(monkeypatch):
    """Real live bug this guards against: speech-to-text mangled
    'pratibhajobs10@gmail.com' into 'pratibha jobstand at gmail.com' (the
    literal word "at", no "@" at all) -- propose_booking used to accept
    that as-is and read it back verbatim, producing a nonsensical
    confirmation. Anything not shaped like local@domain.tld must be
    rejected here, deterministically, instead of ever reaching
    _call_pending_confirmation."""
    monkeypatch.setattr(settings, "twilio_auth_token", "")
    monkeypatch.setattr(agents_voice, "_retrieve_context", lambda db, query, **kwargs: "")
    call_sid = "CAtest-malformed-email"
    agents_voice._forget_call(call_sid)

    monday = datetime.now(timezone.utc) + timedelta(days=(7 - datetime.now(timezone.utc).weekday()))
    slots = [booking_service.SlotOption(start=monday.replace(hour=14, minute=0), end=monday.replace(hour=14, minute=30))]
    agents_voice._call_pending_slots[call_sid] = slots

    propose_call = ToolCall(
        id="call_1",
        name="propose_booking",
        arguments='{"slot_index": 1, "name": "Pratibha", "email": "pratibha jobstand at gmail.com"}',
    )
    fake_chat = AsyncMock(
        side_effect=[
            _tool_call_result("", propose_call),
            _tool_call_result("Sorry, could you say your email again slowly?"),
        ]
    )
    monkeypatch.setattr(agents_voice._llm_client, "chat", fake_chat)

    resp = client.post(
        "/api/agents/voice/gather",
        data={"CallSid": call_sid, "SpeechResult": "my name is Pratibha and my email is pratibha jobstand at gmail.com"},
    )

    assert resp.status_code == 200
    assert "say your email again" in resp.text
    assert call_sid not in agents_voice._call_pending_confirmation


def test_gather_finalizes_booking_on_the_next_turns_confirmation_with_no_further_llm_call(monkeypatch):
    """The two-turn shape: propose_booking stages a confirmation on turn N,
    and the caller's plain "yes" on turn N+1 books it -- using exactly the
    slot/name/email already staged, never re-derived from another LLM tool
    call (no fake_chat return value is even queued for this turn, so an
    unexpected LLM call here would raise StopAsyncIteration and fail the
    test)."""
    monkeypatch.setattr(settings, "twilio_auth_token", "")
    call_sid = "CAtest-finalize"
    agents_voice._forget_call(call_sid)

    monday = datetime.now(timezone.utc) + timedelta(days=(7 - datetime.now(timezone.utc).weekday()))
    slots = [booking_service.SlotOption(start=monday.replace(hour=14, minute=0), end=monday.replace(hour=14, minute=30))]
    agents_voice._call_pending_slots[call_sid] = slots
    agents_voice._call_pending_meeting_type[call_sid] = "call"
    # As if propose_booking staged this on the immediately preceding turn.
    agents_voice._call_turn_counts[call_sid] = 1
    agents_voice._call_pending_confirmation[call_sid] = {
        "turn": 1, "slot_index": 1, "name": "John", "email": "john@example.com", "phone": None,
    }
    fake_booking = type("FakeBooking", (), {"calendar_event_id": "evt-1"})()
    fake_confirm = AsyncMock(
        return_value=booking_service.ConfirmBookingResult(
            status="booked", event_id="evt-1", booking=fake_booking, notify_email=None
        )
    )
    monkeypatch.setattr(booking_service, "confirm_booking_slot", fake_confirm)
    fake_chat = AsyncMock()  # no side_effect queued -- must never be called
    monkeypatch.setattr(agents_voice._llm_client, "chat", fake_chat)

    resp = client.post(
        "/api/agents/voice/gather",
        data={"CallSid": call_sid, "SpeechResult": "Yes, go ahead and book it"},
    )

    assert resp.status_code == 200
    assert "You're all set" in resp.text
    fake_confirm.assert_awaited_once()
    fake_chat.assert_not_awaited()
    assert call_sid not in agents_voice._call_pending_confirmation
    assert call_sid not in agents_voice._call_pending_slots


def test_gather_does_not_finalize_when_the_next_turn_is_not_a_confirmation(monkeypatch):
    """A non-affirmative reply to propose_booking's readback (a correction,
    a new question, anything else) must NOT book, and must clear the
    pending proposal (single-shot) rather than let it linger for a later
    turn to accidentally trigger."""
    monkeypatch.setattr(settings, "twilio_auth_token", "")
    monkeypatch.setattr(agents_voice, "_retrieve_context", lambda db, query, **kwargs: "")
    call_sid = "CAtest-correction"
    agents_voice._forget_call(call_sid)

    monday = datetime.now(timezone.utc) + timedelta(days=(7 - datetime.now(timezone.utc).weekday()))
    slots = [booking_service.SlotOption(start=monday.replace(hour=14, minute=0), end=monday.replace(hour=14, minute=30))]
    agents_voice._call_pending_slots[call_sid] = slots
    agents_voice._call_turn_counts[call_sid] = 1
    agents_voice._call_pending_confirmation[call_sid] = {
        "turn": 1, "slot_index": 1, "name": "John", "email": "wrong@example.com", "phone": None,
    }
    fake_confirm = AsyncMock()
    monkeypatch.setattr(booking_service, "confirm_booking_slot", fake_confirm)
    fake_chat = AsyncMock(return_value=_tool_call_result("Got it, what's the correct email?"))
    monkeypatch.setattr(agents_voice._llm_client, "chat", fake_chat)

    resp = client.post(
        "/api/agents/voice/gather",
        data={"CallSid": call_sid, "SpeechResult": "no, that email is wrong"},
    )

    assert resp.status_code == 200
    fake_confirm.assert_not_awaited()
    assert call_sid not in agents_voice._call_pending_confirmation
    # Fell through to the normal LLM turn instead of silently dropping the
    # caller's correction.
    fake_chat.assert_awaited_once()


def test_pending_confirmation_does_not_fire_on_a_later_unrelated_yes(monkeypatch):
    """Safety property: propose_booking's confirmation is single-shot and
    turn-scoped. If the caller doesn't answer it on the very next turn, it
    must not be sitting around to get accidentally triggered by an
    unrelated "yes" on some later turn."""
    monkeypatch.setattr(settings, "twilio_auth_token", "")
    monkeypatch.setattr(agents_voice, "_retrieve_context", lambda db, query, **kwargs: "")
    call_sid = "CAtest-stale-confirm"
    agents_voice._forget_call(call_sid)

    monday = datetime.now(timezone.utc) + timedelta(days=(7 - datetime.now(timezone.utc).weekday()))
    slots = [booking_service.SlotOption(start=monday.replace(hour=14, minute=0), end=monday.replace(hour=14, minute=30))]
    agents_voice._call_pending_slots[call_sid] = slots
    # Staged on turn 1, but the caller's very next turn (turn 2, below)
    # asks something unrelated instead of confirming -- by the time turn 3
    # says "yes" to that unrelated thing, the proposal must already be gone.
    agents_voice._call_turn_counts[call_sid] = 1
    agents_voice._call_pending_confirmation[call_sid] = {
        "turn": 1, "slot_index": 1, "name": "John", "email": "john@example.com", "phone": None,
    }
    fake_confirm = AsyncMock()
    monkeypatch.setattr(booking_service, "confirm_booking_slot", fake_confirm)
    fake_chat = AsyncMock(
        side_effect=[
            _tool_call_result("Sure, we're open weekdays 9 to 5."),
            _tool_call_result("Glad that helps!"),
        ]
    )
    monkeypatch.setattr(agents_voice._llm_client, "chat", fake_chat)

    turn_two = client.post(
        "/api/agents/voice/gather",
        data={"CallSid": call_sid, "SpeechResult": "actually what are your hours"},
    )
    assert turn_two.status_code == 200
    assert call_sid not in agents_voice._call_pending_confirmation

    turn_three = client.post(
        "/api/agents/voice/gather",
        data={"CallSid": call_sid, "SpeechResult": "yes that's great, thanks"},
    )

    assert turn_three.status_code == 200
    fake_confirm.assert_not_awaited()


def test_gather_falls_back_after_exhausting_tool_rounds(monkeypatch):
    """The model still wanting another tool call after _MAX_TOOL_ROUNDS+1
    LLM calls must degrade to the fallback line, not loop forever or hang
    the webhook past Twilio's own response budget."""
    monkeypatch.setattr(settings, "twilio_auth_token", "")
    monkeypatch.setattr(agents_voice, "_retrieve_context", lambda db, query, **kwargs: "")
    call_sid = "CAtest-toolcap"
    agents_voice._forget_call(call_sid)

    monkeypatch.setattr(
        booking_service,
        "resolve_booking_request",
        AsyncMock(return_value=booking_service.ResolveBookingResult(status="clarification_needed")),
    )
    always_wants_a_tool = ToolCall(id="call_x", name="check_availability", arguments='{"description": "something"}')
    fake_chat = AsyncMock(return_value=_tool_call_result("", always_wants_a_tool))
    monkeypatch.setattr(agents_voice._llm_client, "chat", fake_chat)

    resp = client.post(
        "/api/agents/voice/gather",
        data={"CallSid": call_sid, "SpeechResult": "book me something"},
    )

    assert resp.status_code == 200
    assert agents_voice._TOOL_LOOP_FALLBACK in resp.text
    assert fake_chat.await_count == agents_voice._MAX_TOOL_ROUNDS + 1


def test_gather_books_across_the_full_check_propose_confirm_flow(monkeypatch):
    """The real three-turn shape end to end: turn 1 offers times
    (check_availability), turn 2 stages a confirmation (propose_booking,
    short-circuited -- no LLM narration call), turn 3 books it on the
    caller's plain "yes" (_finalize_booking, no LLM call at all) -- three
    separate webhook calls, so three genuinely different turn_counts."""
    monkeypatch.setattr(settings, "twilio_auth_token", "")
    monkeypatch.setattr(agents_voice, "_retrieve_context", lambda db, query, **kwargs: "")
    call_sid = "CAtest-threeturn"
    agents_voice._forget_call(call_sid)

    monday = datetime.now(timezone.utc) + timedelta(days=(7 - datetime.now(timezone.utc).weekday()))
    slots = [booking_service.SlotOption(start=monday.replace(hour=14, minute=0), end=monday.replace(hour=14, minute=30))]
    monkeypatch.setattr(
        booking_service,
        "resolve_booking_request",
        AsyncMock(
            return_value=booking_service.ResolveBookingResult(
                status="needs_selection", slots=slots, meeting_type="call", duration_minutes=30
            )
        ),
    )
    check_call = ToolCall(id="call_1", name="check_availability", arguments='{"description": "a call"}')
    monkeypatch.setattr(
        agents_voice._llm_client,
        "chat",
        AsyncMock(
            side_effect=[
                _tool_call_result("", check_call),
                _tool_call_result("Tuesday at 2 PM is open -- does that work?"),
            ]
        ),
    )
    turn_one = client.post(
        "/api/agents/voice/gather",
        data={"CallSid": call_sid, "SpeechResult": "book me a call"},
    )
    assert turn_one.status_code == 200

    propose_call = ToolCall(
        id="call_2",
        name="propose_booking",
        arguments='{"slot_index": 1, "name": "John", "email": "john@example.com"}',
    )
    # Only one LLMResult queued for turn 2 -- propose_booking short-circuits
    # before a second (narration) LLM call would happen.
    monkeypatch.setattr(
        agents_voice._llm_client, "chat", AsyncMock(side_effect=[_tool_call_result("", propose_call)])
    )
    turn_two = client.post(
        "/api/agents/voice/gather",
        data={"CallSid": call_sid, "SpeechResult": "Tuesday at 2 works, I'm John, john@example.com"},
    )
    assert turn_two.status_code == 200
    assert "Shall I book it" in turn_two.text

    fake_booking = type("FakeBooking", (), {"calendar_event_id": "evt-1"})()
    fake_confirm_result = booking_service.ConfirmBookingResult(
        status="booked", event_id="evt-1", booking=fake_booking, notify_email="owner@example.com"
    )
    fake_confirm = AsyncMock(return_value=fake_confirm_result)
    monkeypatch.setattr(booking_service, "confirm_booking_slot", fake_confirm)
    fake_notify_task = AsyncMock()
    monkeypatch.setattr(agents_voice, "notify_new_booking", fake_notify_task)
    # No LLMResult queued for turn 3 at all -- _finalize_booking must not
    # call the LLM; an unexpected call here would raise StopAsyncIteration.
    monkeypatch.setattr(agents_voice._llm_client, "chat", AsyncMock())

    turn_three = client.post(
        "/api/agents/voice/gather",
        data={"CallSid": call_sid, "SpeechResult": "yes, go ahead"},
    )

    assert turn_three.status_code == 200
    assert "You're all set" in turn_three.text
    fake_confirm.assert_awaited_once()
    # confirm_booking_slot(db, business_id, start, end, timezone, name, email, phone, meeting_type, session_id)
    awaited_args = fake_confirm.await_args.args
    assert awaited_args[5] == "John"
    assert awaited_args[6] == "john@example.com"
    assert call_sid not in agents_voice._call_pending_slots
    assert call_sid not in agents_voice._call_pending_confirmation


@pytest.mark.asyncio
async def test_fire_booking_notification_schedules_a_kept_task(monkeypatch):
    fake_notify = AsyncMock()
    monkeypatch.setattr(agents_voice, "notify_new_booking", fake_notify)
    fake_booking = object()
    result = booking_service.ConfirmBookingResult(
        status="booked", event_id="evt-1", booking=fake_booking, notify_email="owner@example.com"
    )

    agents_voice._fire_booking_notification(result)

    assert len(agents_voice._pending_notification_tasks) == 1
    task = next(iter(agents_voice._pending_notification_tasks))
    await task
    fake_notify.assert_awaited_once_with("owner@example.com", fake_booking)
    # add_done_callback(discard) should have removed it once it completed.
    assert len(agents_voice._pending_notification_tasks) == 0


def test_fire_booking_notification_noop_without_notify_email(monkeypatch):
    fake_notify = AsyncMock()
    monkeypatch.setattr(agents_voice, "notify_new_booking", fake_notify)
    result = booking_service.ConfirmBookingResult(status="booked", event_id="evt-1", booking=None, notify_email=None)

    agents_voice._fire_booking_notification(result)

    assert len(agents_voice._pending_notification_tasks) == 0
    fake_notify.assert_not_called()


def test_gather_create_support_ticket_tool_creates_escalated_ticket(monkeypatch):
    """Phase 5 (apps/agents/support-triage/CLAUDE.md): Voice Receptionist
    hands a caller's issue off to Support Triage as a direct function call,
    not HTTP -- see apps/agents/CLAUDE.md, "How the three agents talk to
    each other"."""
    monkeypatch.setattr(settings, "twilio_auth_token", "")
    monkeypatch.setattr(agents_voice, "_retrieve_context", lambda db, query, **kwargs: "")
    call_sid = "CAtest-supportticket"
    agents_voice._forget_call(call_sid)
    agents_voice._call_caller_number[call_sid] = "+15559876543"

    fake_create_ticket = AsyncMock(
        return_value=support_service.TicketResult(ticket_id="tix-123", status="escalated")
    )
    monkeypatch.setattr(support_service, "create_ticket", fake_create_ticket)

    tool_call = ToolCall(
        id="call_1",
        name="create_support_ticket",
        arguments='{"customer_name": "Jane", "issue_description": "Says her invoice total looks wrong."}',
    )
    fake_chat = AsyncMock(
        side_effect=[
            _tool_call_result("", tool_call),
            _tool_call_result("I've flagged this for our team -- someone will follow up with you soon."),
        ]
    )
    monkeypatch.setattr(agents_voice._llm_client, "chat", fake_chat)

    resp = client.post(
        "/api/agents/voice/gather",
        data={"CallSid": call_sid, "SpeechResult": "my invoice total looks wrong, can someone help"},
    )

    assert resp.status_code == 200
    assert "follow up with you soon" in resp.text
    fake_create_ticket.assert_awaited_once()
    awaited_kwargs = fake_create_ticket.await_args.kwargs
    assert awaited_kwargs["channel"] == "voice"
    assert awaited_kwargs["customer_name"] == "Jane"
    assert awaited_kwargs["customer_phone"] == "+15559876543"
    assert awaited_kwargs["issue_description"] == "Says her invoice total looks wrong."


def test_gather_create_support_ticket_tool_requires_name_and_issue(monkeypatch):
    monkeypatch.setattr(settings, "twilio_auth_token", "")
    monkeypatch.setattr(agents_voice, "_retrieve_context", lambda db, query, **kwargs: "")
    call_sid = "CAtest-supportticket-missing"
    agents_voice._forget_call(call_sid)

    fake_create_ticket = AsyncMock()
    monkeypatch.setattr(support_service, "create_ticket", fake_create_ticket)

    tool_call = ToolCall(id="call_1", name="create_support_ticket", arguments='{"customer_name": ""}')
    fake_chat = AsyncMock(
        side_effect=[
            _tool_call_result("", tool_call),
            _tool_call_result("Could I get your name and a quick description of the issue?"),
        ]
    )
    monkeypatch.setattr(agents_voice._llm_client, "chat", fake_chat)

    resp = client.post(
        "/api/agents/voice/gather",
        data={"CallSid": call_sid, "SpeechResult": "I have a problem"},
    )

    assert resp.status_code == 200
    fake_create_ticket.assert_not_awaited()


# --- Norwegian language support -----------------------------------------


def test_incoming_call_always_gathers_in_english(monkeypatch):
    """A brand-new call has no language history yet -- the very first
    <Gather> must always request English recognition, never Norwegian,
    regardless of what a previous call on the same process did."""
    monkeypatch.setattr(settings, "twilio_auth_token", "")
    resp = client.post("/api/agents/voice/incoming", data={"CallSid": "CAtest-freshcall"})

    assert resp.status_code == 200
    assert 'language="en-US"' in resp.text


def test_gather_latches_to_norwegian_and_switches_recognition_language(monkeypatch):
    """A caller who replies in Norwegian flips this call's language to
    "no" -- both the LLM's reply-language instruction (checked indirectly
    via the system prompt below) and, critically, the NEXT <Gather>'s own
    Twilio recognition language, so a real follow-up sentence actually
    gets transcribed correctly instead of staying stuck on English."""
    monkeypatch.setattr(settings, "twilio_auth_token", "")
    monkeypatch.setattr(agents_voice, "_retrieve_context", lambda db, query, **kwargs: "")
    call_sid = "CAtest-norwegian-latch"
    agents_voice._forget_call(call_sid)

    fake_chat = AsyncMock(return_value=_tool_call_result("Hei! Hvordan kan jeg hjelpe deg?"))
    monkeypatch.setattr(agents_voice._llm_client, "chat", fake_chat)

    resp = client.post(
        "/api/agents/voice/gather",
        data={"CallSid": call_sid, "SpeechResult": "Hei, jeg vil gjerne bestille en time, takk"},
    )

    assert resp.status_code == 200
    assert 'language="nb-NO"' in resp.text
    assert agents_voice._call_language[call_sid] == "no"
    system_message = fake_chat.call_args.args[0][0]["content"]
    assert "reply ONLY in Norwegian" in system_message


def test_gather_norwegian_stays_latched_on_an_ambiguous_later_turn(monkeypatch):
    """Once switched, the call must not flip back to English mid-call just
    because a later turn's speech happens to score ambiguously (e.g. a
    short reply with no strong signal either way) -- that would whiplash
    the caller. The latch is one-directional."""
    monkeypatch.setattr(settings, "twilio_auth_token", "")
    monkeypatch.setattr(agents_voice, "_retrieve_context", lambda db, query, **kwargs: "")
    call_sid = "CAtest-norwegian-sticky"
    agents_voice._forget_call(call_sid)
    agents_voice._call_language[call_sid] = "no"
    agents_voice._call_history[call_sid] = []

    fake_chat = AsyncMock(return_value=_tool_call_result("..."))
    monkeypatch.setattr(agents_voice._llm_client, "chat", fake_chat)

    resp = client.post(
        "/api/agents/voice/gather",
        data={"CallSid": call_sid, "SpeechResult": "12"},
    )

    assert resp.status_code == 200
    assert agents_voice._call_language[call_sid] == "no"
    assert 'language="nb-NO"' in resp.text


def test_gather_norwegian_goodbye_phrase_ends_call_in_norwegian(monkeypatch):
    monkeypatch.setattr(settings, "twilio_auth_token", "")
    call_sid = "CAtest-norwegian-bye"
    agents_voice._forget_call(call_sid)
    agents_voice._call_language[call_sid] = "no"
    agents_voice._call_history[call_sid] = []

    resp = client.post(
        "/api/agents/voice/gather",
        data={"CallSid": call_sid, "SpeechResult": "Nei takk, det var alt. Ha det!"},
    )

    assert resp.status_code == 200
    assert agents_voice._CLOSING_LINE_NO in resp.text
    assert "<Hangup" in resp.text
    assert call_sid not in agents_voice._call_language


def test_gather_norwegian_confirmation_books_and_replies_in_norwegian(monkeypatch):
    """The deterministic finalize-booking fast path must also recognize a
    Norwegian "yes" (e.g. "ja, det stemmer") -- the English-only
    _CONFIRMATION_PATTERN would otherwise silently strand a Norwegian
    caller one turn away from ever completing a real booking."""
    monkeypatch.setattr(settings, "twilio_auth_token", "")
    call_sid = "CAtest-norwegian-confirm"
    agents_voice._forget_call(call_sid)
    agents_voice._call_language[call_sid] = "no"
    agents_voice._call_history[call_sid] = []
    agents_voice._call_turn_counts[call_sid] = 1
    monday = datetime.now(timezone.utc) + timedelta(days=(7 - datetime.now(timezone.utc).weekday()))
    slot = booking_service.SlotOption(start=monday.replace(hour=14, minute=0), end=monday.replace(hour=14, minute=30))
    agents_voice._call_pending_slots[call_sid] = [slot]
    agents_voice._call_pending_meeting_type[call_sid] = "call"
    agents_voice._call_pending_confirmation[call_sid] = {
        "turn": 1,
        "slot_index": 1,
        "name": "Kari",
        "email": "kari@example.com",
        "phone": None,
    }

    fake_booking = type("FakeBooking", (), {"calendar_event_id": "evt-no-1"})()
    fake_confirm_result = booking_service.ConfirmBookingResult(
        status="booked", event_id="evt-no-1", booking=fake_booking, notify_email="owner@example.com"
    )
    monkeypatch.setattr(booking_service, "confirm_booking_slot", AsyncMock(return_value=fake_confirm_result))
    monkeypatch.setattr(agents_voice, "notify_new_booking", AsyncMock())
    # No LLMResult queued -- the Norwegian confirmation fast path must skip
    # the LLM entirely, same as the English one.
    monkeypatch.setattr(agents_voice._llm_client, "chat", AsyncMock())

    resp = client.post(
        "/api/agents/voice/gather",
        data={"CallSid": call_sid, "SpeechResult": "ja, det stemmer"},
    )

    assert resp.status_code == 200
    assert "Da er du booket" in resp.text
    assert agents_voice._format_slot_for_speech(slot.start, "no") in resp.text


def test_dev_gather_reports_current_language_for_the_browser_demo(monkeypatch):
    """The browser demo has no server-side Gather/Say to configure -- it
    reads this field back to switch its own Web Speech API recognizer and
    voice once a call latches onto Norwegian."""
    monkeypatch.setattr(agents_voice, "_retrieve_context", lambda db, query, **kwargs: "")
    call_sid = "CAdevtest-norwegian"
    agents_voice._forget_call(call_sid)

    fake_chat = AsyncMock(return_value=_tool_call_result("Hei! Hvordan kan jeg hjelpe deg?"))
    monkeypatch.setattr(agents_voice._llm_client, "chat", fake_chat)

    resp = client.post(
        "/api/agents/voice/dev/gather",
        json={"call_sid": call_sid, "speech": "Hei, jeg har et spørsmål, takk"},
    )

    assert resp.status_code == 200
    assert resp.json()["language"] == "no"
