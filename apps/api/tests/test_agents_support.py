"""
Support Triage -- Phase 0 + Phase 1 tests (see
apps/agents/support-triage/CLAUDE.md). The LLM client and RAG context
retrieval are always mocked here (same convention as test_agents_voice.py)
-- no test makes a real Groq call or loads the real embedding model.
"""

import json
from unittest.mock import AsyncMock

import pytest

from app.core.config import settings
from app.models.ticket import Ticket, TicketMessage
from app.services import support_service
from mielikkix_agent_core import LLMResult


def _fake_llm_response(json_text: str) -> LLMResult:
    return LLMResult(text=json_text, usage=None)


@pytest.fixture(autouse=True)
def _no_rag_context(monkeypatch):
    """Every test in this file mocks the LLM response directly, so context
    retrieval (which would otherwise need a real business/embeddings) is
    always stubbed out to "" -- same pattern test_agents_voice.py uses for
    its own _retrieve_context."""
    monkeypatch.setattr(support_service, "_retrieve_context", lambda db, query: "")


def _mock_classification(monkeypatch, category="general", priority="low", confidence=0.9, answer="Here's the answer."):
    fake_chat = AsyncMock(
        return_value=_fake_llm_response(
            json.dumps({"category": category, "priority": priority, "confidence": confidence, "answer": answer})
        )
    )
    monkeypatch.setattr(support_service._llm_client, "chat", fake_chat)
    return fake_chat


def _post(client, session_id, message, customer_email=None):
    return client.post(
        "/api/agents/support/chat/message",
        json={"session_id": session_id, "message": message, "customer_email": customer_email},
    )


def test_confident_classification_answers_directly_and_stores_fields(client, db_session, monkeypatch):
    _mock_classification(monkeypatch, category="pricing", priority="medium", confidence=0.85, answer="It's $10/mo.")

    resp = _post(client, "sess-1", "how much does it cost?")

    assert resp.status_code == 200
    body = resp.json()
    assert body["reply"] == "It's $10/mo."
    assert body["escalated"] is False

    ticket = db_session.query(Ticket).filter(Ticket.id == body["ticket_id"]).first()
    assert ticket.category == "pricing"
    assert ticket.priority == "medium"
    assert ticket.confidence == 0.85


def test_low_confidence_falls_back_and_escalates(client, db_session, monkeypatch):
    monkeypatch.setattr(settings, "support_agent_confidence_threshold", 0.6)
    _mock_classification(monkeypatch, confidence=0.2, answer="Maybe it's this? Not sure.")

    resp = _post(client, "sess-2", "some obscure question")

    body = resp.json()
    assert "Maybe it's this? Not sure." not in body["reply"]
    assert "follow up" in body["reply"]
    assert body["escalated"] is True

    # The classification itself is still recorded, and the ticket is marked
    # escalated (Phase 2) rather than left open with no one to act on it.
    ticket = db_session.query(Ticket).filter(Ticket.id == body["ticket_id"]).first()
    assert ticket.confidence == 0.2
    assert ticket.status == "escalated"


def test_high_priority_escalates_even_at_high_confidence(client, db_session, monkeypatch):
    _mock_classification(monkeypatch, priority="urgent", confidence=0.95, answer="Here's a confident answer.")

    resp = _post(client, "sess-urgent", "the site is completely down for everyone")

    body = resp.json()
    assert body["escalated"] is True
    assert "Here's a confident answer." not in body["reply"]

    ticket = db_session.query(Ticket).filter(Ticket.id == body["ticket_id"]).first()
    assert ticket.status == "escalated"
    assert ticket.priority == "urgent"


def test_confidence_exactly_at_threshold_answers_directly(client, monkeypatch):
    monkeypatch.setattr(settings, "support_agent_confidence_threshold", 0.6)
    _mock_classification(monkeypatch, confidence=0.6, answer="Right at the line.")

    resp = _post(client, "sess-3", "question")

    assert resp.json()["reply"] == "Right at the line."


def test_malformed_llm_json_falls_back_gracefully_and_escalates(client, monkeypatch):
    fake_chat = AsyncMock(return_value=_fake_llm_response("not valid json at all"))
    monkeypatch.setattr(support_service._llm_client, "chat", fake_chat)

    resp = _post(client, "sess-4", "hello")

    assert resp.status_code == 200
    body = resp.json()
    assert "trouble understanding" in body["reply"]
    assert body["escalated"] is True


def test_llm_failure_falls_back_gracefully_and_escalates(client, monkeypatch):
    fake_chat = AsyncMock(side_effect=RuntimeError("groq is down"))
    monkeypatch.setattr(support_service._llm_client, "chat", fake_chat)

    resp = _post(client, "sess-5", "hello")

    assert resp.status_code == 200
    body = resp.json()
    assert "trouble understanding" in body["reply"]
    assert body["escalated"] is True


def test_second_message_same_session_reuses_ticket(client, db_session, monkeypatch):
    _mock_classification(monkeypatch, answer="first reply")
    first = _post(client, "sess-reuse", "first message").json()

    _mock_classification(monkeypatch, answer="second reply")
    second = _post(client, "sess-reuse", "second message").json()

    assert first["ticket_id"] == second["ticket_id"]
    ticket_count = db_session.query(Ticket).filter(Ticket.session_id == "sess-reuse").count()
    assert ticket_count == 1

    messages = (
        db_session.query(TicketMessage)
        .filter(TicketMessage.ticket_id == first["ticket_id"])
        .order_by(TicketMessage.created_at)
        .all()
    )
    assert [m.content for m in messages] == [
        "first message",
        "first reply",
        "second message",
        "second reply",
    ]


def test_different_sessions_get_different_tickets(client, monkeypatch):
    _mock_classification(monkeypatch)
    first = _post(client, "sess-a", "hi").json()
    second = _post(client, "sess-b", "hi").json()

    assert first["ticket_id"] != second["ticket_id"]


def test_customer_email_stored_on_new_ticket(client, db_session, monkeypatch):
    _mock_classification(monkeypatch)
    body = _post(client, "sess-email", "hi", customer_email="visitor@example.com").json()

    ticket = db_session.query(Ticket).filter(Ticket.id == body["ticket_id"]).first()
    assert ticket.customer_email == "visitor@example.com"


def test_booking_shaped_message_skips_classification_and_suggests_booking_flow(client, db_session, monkeypatch):
    fake_chat = AsyncMock(side_effect=AssertionError("the LLM classifier should not be called for a booking intent"))
    monkeypatch.setattr(support_service._llm_client, "chat", fake_chat)

    resp = _post(client, "sess-booking", "I'd like to book an appointment for next week")

    assert resp.status_code == 200
    body = resp.json()
    assert body["suggest_booking_flow"] is True
    assert body["escalated"] is False

    ticket = db_session.query(Ticket).filter(Ticket.id == body["ticket_id"]).first()
    assert ticket.category == "booking"


def test_non_booking_message_does_not_suggest_booking_flow(client, monkeypatch):
    _mock_classification(monkeypatch)
    body = _post(client, "sess-not-booking", "what does the free plan include?").json()

    assert body["suggest_booking_flow"] is False


@pytest.mark.asyncio
async def test_create_ticket_always_escalates_immediately(db_session, monkeypatch):
    sent = []

    async def _fake_notify(ticket):
        sent.append(ticket.id)

    monkeypatch.setattr(support_service, "notify_support_escalation", _fake_notify)

    result = await support_service.create_ticket(
        db_session,
        channel="voice",
        customer_name="Jane Caller",
        customer_phone="+15551234567",
        issue_description="Caller says their invoice looks wrong.",
    )

    assert result.status == "escalated"
    ticket = db_session.query(Ticket).filter(Ticket.id == result.ticket_id).first()
    assert ticket.channel == "voice"
    assert ticket.status == "escalated"
    assert ticket.customer_name == "Jane Caller"
    assert ticket.customer_phone == "+15551234567"
    assert sent == [ticket.id]

    messages = db_session.query(TicketMessage).filter(TicketMessage.ticket_id == ticket.id).all()
    assert [m.content for m in messages] == ["Caller says their invoice looks wrong."]
