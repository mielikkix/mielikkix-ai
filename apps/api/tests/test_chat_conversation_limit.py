"""Tests for the monthly AI-conversation cap (chat_service.handle_message)
and the plan-gated conversation history retention window
(GET /api/chat/conversations).

handle_message normally calls the real RAG pipeline (embeddings + an LLM
provider) -- these tests mock that out so they're fast, offline, and don't
depend on GROQ_API_KEY/network being available.
"""
import uuid
from datetime import datetime, timedelta, timezone

import pytest

from app.services import chat_service
from app.schemas.chat import ChatMessageRequest
from app.models.conversation import Conversation
from fastapi import HTTPException


async def fake_run_rag(**kwargs):
    return "a canned reply", "faq", 0.9


@pytest.mark.asyncio
async def test_new_conversation_allowed_under_cap(db_session, business, monkeypatch):
    monkeypatch.setattr(chat_service, "run_rag", fake_run_rag)
    req = ChatMessageRequest(business_id=business["business_id"], session_id="s1", message="hi")
    resp = await chat_service.handle_message(db_session, req)
    assert resp.reply == "a canned reply"


@pytest.mark.asyncio
async def test_new_conversation_blocked_at_monthly_cap(db_session, business, monkeypatch):
    monkeypatch.setattr(chat_service, "run_rag", fake_run_rag)

    # Free plan cap is 50 conversations/month -- seed 50 directly rather
    # than sending 50 real messages through the (rate-limited) HTTP endpoint.
    for _ in range(50):
        db_session.add(Conversation(business_id=business["business_id"], session_id=uuid.uuid4().hex))
    db_session.commit()

    req = ChatMessageRequest(business_id=business["business_id"], session_id="brand-new-session", message="hi")
    with pytest.raises(HTTPException) as exc:
        await chat_service.handle_message(db_session, req)
    assert exc.value.status_code == 402


@pytest.mark.asyncio
async def test_continuing_an_existing_conversation_is_never_blocked(db_session, business, monkeypatch):
    monkeypatch.setattr(chat_service, "run_rag", fake_run_rag)

    for _ in range(49):
        db_session.add(Conversation(business_id=business["business_id"], session_id=uuid.uuid4().hex))
    db_session.commit()

    # This session starts the 50th conversation -- still within the cap.
    req = ChatMessageRequest(business_id=business["business_id"], session_id="ongoing", message="hi")
    await chat_service.handle_message(db_session, req)

    # Sending a second message in that *same* session must not be blocked,
    # even though the business is now exactly at its 50-conversation cap.
    req2 = ChatMessageRequest(business_id=business["business_id"], session_id="ongoing", message="follow-up")
    resp = await chat_service.handle_message(db_session, req2)
    assert resp.reply == "a canned reply"


# ---------------------------------------------------------------------------
# Conversation history retention window
# ---------------------------------------------------------------------------

def test_history_hides_conversations_older_than_free_plan_window(client, business, db_session):
    recent = Conversation(business_id=business["business_id"], session_id="recent")
    old = Conversation(business_id=business["business_id"], session_id="old")
    old.started_at = datetime.now(timezone.utc) - timedelta(days=30)  # Free plan window is 7 days
    db_session.add_all([recent, old])
    db_session.commit()

    resp = client.get("/api/chat/conversations", headers=business["headers"])
    assert resp.status_code == 200
    session_ids = {c["session_id"] for c in resp.json()}
    assert session_ids == {"recent"}


def test_history_unlimited_on_business_plan(client, business, db_session, set_plan):
    set_plan(business["business_id"], "business")
    old = Conversation(business_id=business["business_id"], session_id="ancient")
    old.started_at = datetime.now(timezone.utc) - timedelta(days=400)
    db_session.add(old)
    db_session.commit()

    resp = client.get("/api/chat/conversations", headers=business["headers"])
    session_ids = {c["session_id"] for c in resp.json()}
    assert "ancient" in session_ids
