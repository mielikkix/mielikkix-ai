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
from app.services import booking_service
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
    assert resp.json() == {"reply": agents_voice._GREETING, "ended": False, "heard_as": None}


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
    assert resp.json() == {"reply": "We're open every day 9 to 6.", "ended": False, "heard_as": None}


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
# book_appointment mid-call (see agents_voice.py's _BOOKING_TOOLS,
# _execute_tool, and the tool-calling loop in _handle_turn). Both
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
    book_appointment(index=1) could silently book a slot the caller never
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


def test_gather_book_appointment_refused_without_a_confirmation_phrase(monkeypatch):
    """The LLM deciding to call book_appointment with no clear affirmative
    anywhere in the caller's own words for this turn must be refused
    server-side -- prompt discipline alone isn't enough given Twilio's
    speech-to-text isn't perfectly reliable."""
    monkeypatch.setattr(settings, "twilio_auth_token", "")
    monkeypatch.setattr(agents_voice, "_retrieve_context", lambda db, query, **kwargs: "")
    call_sid = "CAtest-noconfirm"
    agents_voice._forget_call(call_sid)

    monday = datetime.now(timezone.utc) + timedelta(days=(7 - datetime.now(timezone.utc).weekday()))
    slots = [booking_service.SlotOption(start=monday.replace(hour=14, minute=0), end=monday.replace(hour=14, minute=30))]
    fake_resolve = AsyncMock(
        return_value=booking_service.ResolveBookingResult(
            status="needs_selection", slots=slots, meeting_type="call", duration_minutes=30
        )
    )
    monkeypatch.setattr(booking_service, "resolve_booking_request", fake_resolve)
    fake_confirm = AsyncMock()
    monkeypatch.setattr(booking_service, "confirm_booking_slot", fake_confirm)

    check_call = ToolCall(id="call_1", name="check_availability", arguments='{"description": "a call"}')
    book_call = ToolCall(
        id="call_2",
        name="book_appointment",
        arguments='{"slot_index": 1, "name": "John", "email": "john@example.com"}',
    )
    fake_chat = AsyncMock(
        side_effect=[
            _tool_call_result("", check_call),
            _tool_call_result("", book_call),
            _tool_call_result("Let's confirm the details before I book it -- does the time work?"),
        ]
    )
    monkeypatch.setattr(agents_voice._llm_client, "chat", fake_chat)

    # No "yes"/"book it"/"go ahead" etc. anywhere in this -- describing the
    # request isn't the same as confirming it.
    resp = client.post(
        "/api/agents/voice/gather",
        data={"CallSid": call_sid, "SpeechResult": "here is my name John and email john@example.com for the call"},
    )

    assert resp.status_code == 200
    assert "confirm the details" in resp.text
    fake_confirm.assert_not_awaited()
    # The tool-result message fed back to the LLM must have told it why.
    third_call_messages = fake_chat.call_args_list[2].args[0]
    tool_result_message = third_call_messages[-1]
    assert tool_result_message["role"] == "tool"
    assert "confirmation_required" in tool_result_message["content"]


def test_gather_book_appointment_allowed_with_confirmation_even_after_a_redundant_recheck(monkeypatch):
    """Real live bug this guards against: the model redundantly re-calling
    check_availability to double-check a slot already offered in an
    earlier turn, then booking in that SAME turn, must NOT be refused just
    because a check and a book happened in the same turn -- what matters is
    whether the caller's own words for this turn are a clear yes, which
    they are here ("Yes, go ahead and book it")."""
    monkeypatch.setattr(settings, "twilio_auth_token", "")
    monkeypatch.setattr(agents_voice, "_retrieve_context", lambda db, query, **kwargs: "")
    call_sid = "CAtest-recheck-then-book"
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
    fake_booking = type("FakeBooking", (), {"calendar_event_id": "evt-1"})()
    fake_confirm = AsyncMock(
        return_value=booking_service.ConfirmBookingResult(
            status="booked", event_id="evt-1", booking=fake_booking, notify_email=None
        )
    )
    monkeypatch.setattr(booking_service, "confirm_booking_slot", fake_confirm)

    check_call = ToolCall(id="call_1", name="check_availability", arguments='{"description": "a call"}')
    book_call = ToolCall(
        id="call_2",
        name="book_appointment",
        arguments='{"slot_index": 1, "name": "John", "email": "john@example.com"}',
    )
    fake_chat = AsyncMock(
        side_effect=[
            _tool_call_result("", check_call),
            _tool_call_result("", book_call),
            _tool_call_result("You're all set for Tuesday at 2 PM!"),
        ]
    )
    monkeypatch.setattr(agents_voice._llm_client, "chat", fake_chat)

    resp = client.post(
        "/api/agents/voice/gather",
        data={"CallSid": call_sid, "SpeechResult": "Yes, go ahead and book it"},
    )

    assert resp.status_code == 200
    assert "You're all set" in resp.text
    fake_confirm.assert_awaited_once()


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


def test_gather_books_on_a_later_turn_after_check_availability(monkeypatch):
    """The real two-turn shape: turn 1 offers times, turn 2 (a separate
    webhook call, so a different turn_count) books one -- must NOT be
    refused by the same-turn guard, since it's a genuinely different turn."""
    monkeypatch.setattr(settings, "twilio_auth_token", "")
    monkeypatch.setattr(agents_voice, "_retrieve_context", lambda db, query, **kwargs: "")
    call_sid = "CAtest-twoturn"
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

    fake_booking = type("FakeBooking", (), {"calendar_event_id": "evt-1"})()
    fake_confirm_result = booking_service.ConfirmBookingResult(
        status="booked", event_id="evt-1", booking=fake_booking, notify_email="owner@example.com"
    )
    fake_confirm = AsyncMock(return_value=fake_confirm_result)
    monkeypatch.setattr(booking_service, "confirm_booking_slot", fake_confirm)
    fake_notify_task = AsyncMock()
    monkeypatch.setattr(agents_voice, "notify_new_booking", fake_notify_task)
    book_call = ToolCall(
        id="call_2",
        name="book_appointment",
        arguments='{"slot_index": 1, "name": "John", "email": "john@example.com"}',
    )
    monkeypatch.setattr(
        agents_voice._llm_client,
        "chat",
        AsyncMock(
            side_effect=[
                _tool_call_result("", book_call),
                _tool_call_result("You're all set for Tuesday at 2 PM!"),
            ]
        ),
    )

    turn_two = client.post(
        "/api/agents/voice/gather",
        data={"CallSid": call_sid, "SpeechResult": "yes, book it, John, john@example.com"},
    )

    assert turn_two.status_code == 200
    assert "You're all set" in turn_two.text
    fake_confirm.assert_awaited_once()
    # confirm_booking_slot(db, business_id, start, end, timezone, name, email, phone, meeting_type, session_id)
    awaited_args = fake_confirm.await_args.args
    assert awaited_args[5] == "John"
    assert awaited_args[6] == "john@example.com"
    assert call_sid not in agents_voice._call_pending_slots


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
