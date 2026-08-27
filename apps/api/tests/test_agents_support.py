"""
Support Triage -- Phase 0 + Phase 1 tests (see
apps/agents/support-triage/CLAUDE.md). The LLM client and RAG context
retrieval are always mocked here (same convention as test_agents_voice.py)
-- no test makes a real Groq call or loads the real embedding model.
"""

import json
from unittest.mock import AsyncMock

import pytest

from app.api import agents_support
from app.core.config import settings
from app.models.ticket import Ticket, TicketMessage
from mielikkix_agent_core import LLMResult


def _fake_llm_response(json_text: str) -> LLMResult:
    return LLMResult(text=json_text, usage=None)


@pytest.fixture(autouse=True)
def _no_rag_context(monkeypatch):
    """Every test in this file mocks the LLM response directly, so context
    retrieval (which would otherwise need a real business/embeddings) is
    always stubbed out to "" -- same pattern test_agents_voice.py uses for
    its own _retrieve_context."""
    monkeypatch.setattr(agents_support, "_retrieve_context", lambda db, query: "")


def _mock_classification(monkeypatch, category="general", priority="low", confidence=0.9, answer="Here's the answer."):
    fake_chat = AsyncMock(
        return_value=_fake_llm_response(
            json.dumps({"category": category, "priority": priority, "confidence": confidence, "answer": answer})
        )
    )
    monkeypatch.setattr(agents_support._llm_client, "chat", fake_chat)
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


def test_low_confidence_falls_back_instead_of_answering(client, db_session, monkeypatch):
    monkeypatch.setattr(settings, "support_agent_confidence_threshold", 0.6)
    _mock_classification(monkeypatch, confidence=0.2, answer="Maybe it's this? Not sure.")

    resp = _post(client, "sess-2", "some obscure question")

    body = resp.json()
    assert "Maybe it's this? Not sure." not in body["reply"]
    assert "follow up" in body["reply"]

    # The classification itself is still recorded, even though its answer
    # wasn't trusted -- Phase 2 will use this to decide whether to escalate.
    ticket = db_session.query(Ticket).filter(Ticket.id == body["ticket_id"]).first()
    assert ticket.confidence == 0.2


def test_confidence_exactly_at_threshold_answers_directly(client, monkeypatch):
    monkeypatch.setattr(settings, "support_agent_confidence_threshold", 0.6)
    _mock_classification(monkeypatch, confidence=0.6, answer="Right at the line.")

    resp = _post(client, "sess-3", "question")

    assert resp.json()["reply"] == "Right at the line."


def test_malformed_llm_json_falls_back_gracefully(client, monkeypatch):
    fake_chat = AsyncMock(return_value=_fake_llm_response("not valid json at all"))
    monkeypatch.setattr(agents_support._llm_client, "chat", fake_chat)

    resp = _post(client, "sess-4", "hello")

    assert resp.status_code == 200
    assert "trouble understanding" in resp.json()["reply"]


def test_llm_failure_falls_back_gracefully(client, monkeypatch):
    fake_chat = AsyncMock(side_effect=RuntimeError("groq is down"))
    monkeypatch.setattr(agents_support._llm_client, "chat", fake_chat)

    resp = _post(client, "sess-5", "hello")

    assert resp.status_code == 200
    assert "trouble understanding" in resp.json()["reply"]


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
