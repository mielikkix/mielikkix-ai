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

    # Free plan cap is 50 conversations/month, plus a 10% grace (55) -- seed
    # 55 directly rather than sending real messages through the (rate-limited)
    # HTTP endpoint.
    for _ in range(55):
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


def test_history_up_to_12_months_on_business_plan(client, business, db_session, set_plan):
    """The website sells Business with "up to 12 months" of history (QA 2026-10-02, M5)."""
    set_plan(business["business_id"], "business")
    for session_id, age_days in [("recent", 200), ("ancient", 400)]:
        conv = Conversation(business_id=business["business_id"], session_id=session_id)
        conv.started_at = datetime.now(timezone.utc) - timedelta(days=age_days)
        db_session.add(conv)
    db_session.commit()

    resp = client.get("/api/chat/conversations", headers=business["headers"])
    session_ids = {c["session_id"] for c in resp.json()}
    assert session_ids == {"recent"}


@pytest.mark.asyncio
async def test_80_percent_warning_email_is_queued_for_the_owner(client, db_session, business, monkeypatch):
    """Through the real route: the 40th of 50 conversations queues exactly one
    warning email to the account owner, and the 41st doesn't queue another."""
    monkeypatch.setattr(chat_service, "run_rag", fake_run_rag)
    sent = []

    async def fake_notify(to_emails, business_name, plan_name, level, used, limit):
        sent.append((to_emails, level, used, limit))

    monkeypatch.setattr(chat_service, "notify_quota_warning", fake_notify)
    for _ in range(39):
        db_session.add(Conversation(business_id=business["business_id"], session_id=uuid.uuid4().hex))
    db_session.commit()

    for session in ("s-40", "s-41"):
        resp = client.post(
            "/api/chat/message",
            json={"business_id": business["business_id"], "session_id": session, "message": "hi"},
        )
        assert resp.status_code == 200
    assert len(sent) == 1
    to_emails, level, used, limit = sent[0]
    assert (level, used, limit) == (80, 40, 50)
    assert to_emails and all("@" in e for e in to_emails)
