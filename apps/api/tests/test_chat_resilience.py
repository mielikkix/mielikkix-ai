"""QA 2026-10-02: conversation transcripts in order (D2), and the Chat Widget
staying responsive when Groq is slow or failing (D6)."""

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest

from app.models.conversation import Conversation, Message
from app.rag import pipeline
from app.rag.providers.groq_provider import GroqProvider


def test_transcript_lists_messages_in_time_order(client, business, db_session):
    """Rows inserted out of order must still come back question -> answer."""
    conv = Conversation(business_id=business["business_id"], session_id="sess_order")
    db_session.add(conv)
    db_session.flush()
    t0 = datetime.now(timezone.utc)
    # Inserted newest-first on purpose.
    for offset, sender, content in [(3, "ai", "A2"), (2, "visitor", "Q2"), (1, "ai", "A1"), (0, "visitor", "Q1")]:
        db_session.add(Message(conversation_id=conv.id, sender=sender, content=content, created_at=t0 + timedelta(seconds=offset)))
    db_session.commit()

    convs = client.get("/api/chat/conversations", headers=business["headers"]).json()

    assert [m["content"] for m in convs[0]["messages"]] == ["Q1", "A1", "Q2", "A2"]


class _RateLimitError(Exception):
    pass


_RateLimitError.__name__ = "RateLimitError"


def _response(text="hello"):
    return SimpleNamespace(
        choices=[SimpleNamespace(message=SimpleNamespace(content=text))],
        usage=SimpleNamespace(prompt_tokens=1, completion_tokens=1, total_tokens=2),
    )


@pytest.mark.asyncio
async def test_groq_retries_a_rate_limit_once_quickly(monkeypatch):
    calls = []

    async def create(**kwargs):
        calls.append(1)
        if len(calls) == 1:
            raise _RateLimitError("429")
        return _response("ok")

    monkeypatch.setattr("app.rag.providers.groq_provider.asyncio.sleep", _no_sleep)
    provider = GroqProvider()
    provider._get_client = lambda: SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=create)))

    assert await provider.generate("hi", "ctx") == "ok"
    assert len(calls) == 2


async def _no_sleep(_seconds):
    return None


@pytest.mark.asyncio
async def test_chat_falls_back_instead_of_erroring_when_the_llm_fails(db_session, business, monkeypatch):
    monkeypatch.setattr(pipeline, "embed_query", lambda q: [0.0])
    monkeypatch.setattr(pipeline, "retrieve_chunks", lambda *a, **k: [("Our hours are 9-5.", 0.9)])
    monkeypatch.setattr(pipeline, "retrieve_faqs", lambda *a, **k: [])
    monkeypatch.setattr(pipeline, "retrieve_products", lambda *a, **k: [])

    class _Down:
        async def generate(self, *a, **k):
            raise RuntimeError("groq down")

    monkeypatch.setattr(pipeline, "get_llm_provider", lambda *a, **k: _Down())

    reply, intent, confidence = await pipeline.run_rag(
        db=db_session, business_id=business["business_id"], message="what are your hours", fallback_message="Ask our team!"
    )

    assert reply == "Ask our team!"
    assert confidence == 0.0
