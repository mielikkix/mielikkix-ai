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

from unittest.mock import AsyncMock

import pytest
from fastapi.testclient import TestClient
from twilio.request_validator import RequestValidator

from app.main import app
from app.core.config import settings
from app.api import agents_voice
from mielikkix_agent_core import LLMResult, LLMUsage

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
