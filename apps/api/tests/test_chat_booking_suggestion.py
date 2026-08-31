"""chat_service.handle_message's suggest_lead_capture / suggest_booking_flow
computation -- run_rag is mocked (same convention as
test_chat_conversation_limit.py) so these are fast and don't depend on a
real LLM/embeddings call.
"""

import pytest

from app.services import chat_service
from app.schemas.chat import ChatMessageRequest


def _fake_run_rag(intent: str, confidence: float):
    async def _run(**kwargs):
        return "a canned reply", intent, confidence

    return _run


@pytest.mark.asyncio
async def test_booking_intent_suppresses_lead_capture_when_booking_enabled(
    db_session, business, set_plan, monkeypatch
):
    """A booking intent almost always also has low confidence (a brand-new
    business has no FAQ/document actually about booking) -- confirmed live,
    this used to also trigger suggest_lead_capture at the same time, so the
    widget showed both a lead form AND a booking panel stacked for the same
    message, and the booking one (the actually-relevant one) was easy to
    miss below the fold."""
    set_plan(business["business_id"], "business")
    monkeypatch.setattr(chat_service, "run_rag", _fake_run_rag("booking", 0.0))

    req = ChatMessageRequest(business_id=business["business_id"], session_id="s1", message="book the meeting")
    resp = await chat_service.handle_message(db_session, req)

    assert resp.suggest_booking_flow is True
    assert resp.suggest_lead_capture is False


@pytest.mark.asyncio
async def test_booking_intent_without_booking_enabled_falls_back_to_lead_capture(db_session, business, monkeypatch):
    """Free plan (business fixture's default) doesn't include
    booking_enabled -- suggest_booking_flow must stay False, and the low
    confidence that comes with it should still surface the lead form
    instead, same as before this business ever tried to offer booking."""
    monkeypatch.setattr(chat_service, "run_rag", _fake_run_rag("booking", 0.0))

    req = ChatMessageRequest(business_id=business["business_id"], session_id="s1", message="book the meeting")
    resp = await chat_service.handle_message(db_session, req)

    assert resp.suggest_booking_flow is False
    assert resp.suggest_lead_capture is True


@pytest.mark.asyncio
async def test_low_confidence_non_booking_intent_still_suggests_lead(db_session, business, set_plan, monkeypatch):
    set_plan(business["business_id"], "business")
    monkeypatch.setattr(chat_service, "run_rag", _fake_run_rag("faq", 0.1))

    req = ChatMessageRequest(business_id=business["business_id"], session_id="s1", message="what are your hours")
    resp = await chat_service.handle_message(db_session, req)

    assert resp.suggest_booking_flow is False
    assert resp.suggest_lead_capture is True


@pytest.mark.asyncio
async def test_lead_intent_still_suggests_lead_regardless_of_confidence(db_session, business, set_plan, monkeypatch):
    set_plan(business["business_id"], "business")
    monkeypatch.setattr(chat_service, "run_rag", _fake_run_rag("lead", 0.9))

    req = ChatMessageRequest(business_id=business["business_id"], session_id="s1", message="I'd like to talk to sales")
    resp = await chat_service.handle_message(db_session, req)

    assert resp.suggest_booking_flow is False
    assert resp.suggest_lead_capture is True
