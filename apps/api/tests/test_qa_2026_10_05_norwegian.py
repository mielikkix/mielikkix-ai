"""Norwegian QA report 2026-10-05: the AI agents didn't follow the site
language. LLM calls, embeddings and the calendar are always mocked here."""

import json
from datetime import date, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from fastapi.testclient import TestClient

from app.api import agents_booking, agents_voice
from app.core.config import settings
from app.main import app
from app.models.business import BusinessSettings
from app.rag import pipeline
from app.rag.language_detect import detect_message_language
from app.rag.pipeline import _detect_intent
from app.schemas.chat import ChatMessageRequest
from app.services import booking_service, chat_service, support_service
from mielikkix_agent_core import LLMResult

client = TestClient(app)


def _next_monday(after: date) -> date:
    return after + timedelta(days=(7 - after.weekday()) or 7)


# --- BUG-02: short Norwegian questions -------------------------------------


@pytest.mark.parametrize(
    "message",
    ["Hvem eier dataene mine?", "Hvordan kan jeg kontakte dere?", "Hva koster det?", "Er det gratis?"],
)
def test_short_norwegian_questions_are_detected(message):
    assert detect_message_language(message, ["en", "no"], default="en") == "no"


def test_english_questions_stay_english():
    assert detect_message_language("Who owns my data?", ["en", "no"], default="no") == "en"


def _settings(db_session, business_id):
    return db_session.query(BusinessSettings).filter(BusinessSettings.business_id == business_id).first()


def _capture_run_rag(seen):
    async def _run(**kwargs):
        seen.append(kwargs)
        return "svar", "faq", 0.9

    return _run


@pytest.mark.asyncio
async def test_ambiguous_message_follows_page_language_then_conversation(db_session, business, monkeypatch):
    s = _settings(db_session, business["business_id"])
    s.languages = ["en", "no"]
    db_session.commit()
    seen = []
    monkeypatch.setattr(chat_service, "run_rag", _capture_run_rag(seen))

    # "Pris?" alone signals nothing; the Norwegian page decides.
    first = await chat_service.handle_message(
        db_session,
        ChatMessageRequest(business_id=business["business_id"], session_id="nor-1", message="Okay?", page_lang="no"),
    )
    assert first.lang == "no"

    # Same conversation, page hint gone: still Norwegian, not the English default.
    second = await chat_service.handle_message(
        db_session, ChatMessageRequest(business_id=business["business_id"], session_id="nor-1", message="Okay?")
    )
    assert second.lang == "no"
    assert seen[-1]["languages"][0] == "no"


# --- BUG-01: contact details ------------------------------------------------


@pytest.mark.asyncio
async def test_contact_details_reach_the_rag_call(db_session, business, monkeypatch):
    s = _settings(db_session, business["business_id"])
    s.contact_email = "post@mielikkix.no, owner-private@example.com"
    s.contact_phone = None
    db_session.commit()
    seen = []
    monkeypatch.setattr(chat_service, "run_rag", _capture_run_rag(seen))

    await chat_service.handle_message(
        db_session,
        ChatMessageRequest(business_id=business["business_id"], session_id="c-1", message="Hvordan kan jeg kontakte dere?"),
    )

    details = seen[-1]["contact_details"]
    assert "post@mielikkix.no" in details
    assert "owner-private" not in details  # only the first (public) address


@pytest.mark.asyncio
async def test_run_rag_adds_contact_details_for_contact_questions_even_without_matches(monkeypatch):
    monkeypatch.setattr(pipeline, "embed_query", lambda text: [1.0])
    for name in ("retrieve_chunks", "retrieve_faqs", "retrieve_products"):
        monkeypatch.setattr(pipeline, name, lambda *a, **k: [])
    contexts = []

    async def _generate(prompt, context, tone, history, languages):
        contexts.append(context)
        return "Du når oss på post@mielikkix.no."

    monkeypatch.setattr(
        pipeline, "get_llm_provider", lambda *a: SimpleNamespace(generate=_generate, last_usage=None)
    )

    reply, intent, _ = await pipeline.run_rag(
        db=None,
        business_id="b",
        message="Hva er e-postadressen deres?",
        contact_details="How to contact this business -- Email: post@mielikkix.no.",
    )

    assert intent == "lead"
    assert "post@mielikkix.no" in contexts[0]
    assert reply == "Du når oss på post@mielikkix.no."


# --- BUG-04: Norwegian buying/contact intent ---------------------------------


@pytest.mark.parametrize(
    "message,expected",
    [
        ("Jeg vil kjøpe Voice Receptionist til frisørsalongen min, kan noen ringe meg?", "lead"),
        ("Hva er e-postadressen deres?", "lead"),
        ("Hvordan kan jeg kontakte dere?", "lead"),
        ("Hva koster Business-planen?", "product_inquiry"),
        ("Kan jeg bestille time på fredag?", "booking"),
        ("Hvem eier dataene mine?", "faq"),
    ],
)
def test_norwegian_intents(message, expected):
    assert _detect_intent(message) == expected


# --- BUG-05/06: booking -----------------------------------------------------


class TestTimeOfDay:
    @pytest.fixture(autouse=True)
    def _hours(self, monkeypatch):
        monkeypatch.setattr(settings, "booking_agent_hours_start", "09:00")
        monkeypatch.setattr(settings, "booking_agent_hours_end", "17:00")

    def test_afternoon_only_returns_afternoon_slots(self):
        monday = _next_monday(date.today())
        slots = booking_service._available_slots_for_range([], monday, monday, 30, "UTC", time_of_day="afternoon")
        assert slots and all(12 <= start.hour < 17 for start, _ in slots)

    def test_slots_are_spread_across_days_in_time_order(self):
        monday = _next_monday(date.today())
        tuesday, next_tuesday = monday + timedelta(days=1), monday + timedelta(days=8)
        slots = booking_service._available_slots_for_range([], tuesday, next_tuesday, 30, "UTC")
        days = {start.date() for start, _ in slots}
        assert len(days) > 1
        assert slots == sorted(slots)
        assert len(slots) == booking_service._MAX_SLOTS_RETURNED


def _mock_parse(monkeypatch, **overrides):
    fields = {
        "duration_minutes": 30,
        "earliest_date": "",
        "latest_date": "",
        "meeting_type": "konsultasjon",
        "clarification_needed": False,
        "clarification_question": "",
    }
    fields.update(overrides)
    monkeypatch.setattr(
        agents_booking._llm_client, "chat", AsyncMock(return_value=LLMResult(text=json.dumps(fields), usage=None))
    )


def test_request_reports_full_afternoon(monkeypatch):
    monkeypatch.setattr(settings, "booking_agent_hours_start", "09:00")
    monkeypatch.setattr(settings, "booking_agent_hours_end", "12:00")
    monday = _next_monday(date.today())
    _mock_parse(monkeypatch, earliest_date=str(monday), latest_date=str(monday), time_of_day="afternoon")
    monkeypatch.setattr(agents_booking._calendar_provider, "get_busy_blocks", AsyncMock(return_value=[]))

    body = client.post("/api/agents/booking/request", json={"message": "mandag ettermiddag", "lang": "no"}).json()

    assert body["status"] == "no_availability"
    assert body["time_of_day"] == "afternoon"


def test_unparsable_request_gets_norwegian_clarification(monkeypatch):
    monkeypatch.setattr(
        agents_booking._llm_client, "chat", AsyncMock(return_value=LLMResult(text="not json", usage=None))
    )

    body = client.post("/api/agents/booking/request", json={"message": "hei", "lang": "no"}).json()

    assert body["status"] == "clarification_needed"
    assert body["clarification_question"].startswith("Beklager")


# --- BUG-07: voice ------------------------------------------------------------


def test_voice_demo_can_start_in_norwegian(monkeypatch):
    monkeypatch.setattr(settings, "debug", True)

    resp = client.post("/api/agents/voice/dev/start", json={"call_sid": "nor-demo-1", "language": "no"})

    assert resp.status_code == 200
    assert resp.json()["reply"] == agents_voice._GREETING_NO
    assert resp.json()["language"] == "no"
    assert agents_voice._call_language["nor-demo-1"] == "no"


# --- BUG-08: support triage ---------------------------------------------------


@pytest.fixture
def _no_support_context(monkeypatch):
    monkeypatch.setattr(support_service, "_retrieve_context", lambda db, query: "")


def _mock_support(monkeypatch, **fields):
    data = {"category": "general", "priority": "low", "confidence": 0.9, "answer": "Svar."}
    data.update(fields)
    monkeypatch.setattr(
        support_service._llm_client, "chat", AsyncMock(return_value=LLMResult(text=json.dumps(data), usage=None))
    )


def test_off_topic_question_is_tagged_and_not_escalated(client, _no_support_context, monkeypatch):
    _mock_support(monkeypatch, off_topic=True, answer="Jeg kan bare hjelpe med spørsmål om Mielikkix.")

    body = client.post(
        "/api/agents/support/chat/message",
        json={"session_id": "nor-s1", "message": "Hvordan blir været i Oslo i morgen?", "lang": "no"},
    ).json()

    assert body["off_topic"] is True
    assert body["escalated"] is False
    assert body["reply"] == "Jeg kan bare hjelpe med spørsmål om Mielikkix."


def test_norwegian_escalation_reply_is_norwegian(client, _no_support_context, monkeypatch):
    _mock_support(monkeypatch, priority="urgent", category="billing")

    body = client.post(
        "/api/agents/support/chat/message",
        json={
            "session_id": "nor-s2",
            "message": "Jeg ble belastet to ganger på fakturaen min, dette er uakseptabelt!",
            "lang": "no",
        },
    ).json()

    assert body["escalated"] is True
    assert body["reply"].startswith("Takk for at du sier fra")
    assert "e-postadresse" in body["reply"]  # the follow-up contact question, in Norwegian too
