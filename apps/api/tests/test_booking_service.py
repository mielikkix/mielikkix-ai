"""Direct, non-HTTP tests of booking_service.py's two public entry points --
these matter on their own now, not just as what test_agents_booking.py's
HTTP-layer tests exercise indirectly, since Voice Receptionist
(agents_voice.py) calls resolve_booking_request()/confirm_booking_slot()
directly, with no FastAPI request/response cycle at all. No test here makes
a real Google Calendar or LLM call.
"""

import json
from datetime import date, datetime, timedelta
from unittest.mock import AsyncMock

import pytest

from app.core.config import settings
from app.integrations.google_calendar_client import BusyBlock, GoogleCalendarError
from app.models.booking import Booking
from app.services import booking_service
from mielikkix_agent_core import LLMResult


def _next_monday(after: date) -> date:
    days_until_monday = (7 - after.weekday()) % 7 or 7
    return after + timedelta(days=days_until_monday + 7)


@pytest.fixture(autouse=True)
def _business_hours(monkeypatch):
    monkeypatch.setattr(settings, "booking_agent_hours_start", "09:00")
    monkeypatch.setattr(settings, "booking_agent_hours_end", "17:00")


def _fake_llm_response(**overrides) -> LLMResult:
    fields = {
        "duration_minutes": 30,
        "earliest_date": "",
        "latest_date": "",
        "meeting_type": "consultation",
        "clarification_needed": False,
        "clarification_question": "",
    }
    fields.update(overrides)
    return LLMResult(text=json.dumps(fields), usage=None)


def _mock_parse(monkeypatch, **overrides):
    fake_chat = AsyncMock(return_value=_fake_llm_response(**overrides))
    monkeypatch.setattr(booking_service._llm_client, "chat", fake_chat)
    return fake_chat


@pytest.mark.asyncio
async def test_resolve_booking_request_returns_slots_when_available(db_session, monkeypatch):
    monday = _next_monday(date.today())
    _mock_parse(monkeypatch, earliest_date=str(monday), latest_date=str(monday))
    monkeypatch.setattr(booking_service._calendar_provider, "get_busy_blocks", AsyncMock(return_value=[]))

    result = await booking_service.resolve_booking_request(db_session, "book a consultation", "UTC", None)

    assert result.status == "needs_selection"
    assert result.meeting_type == "consultation"
    assert result.duration_minutes == 30
    assert len(result.slots) > 0
    assert result.slots[0].start.isoformat() == f"{monday}T09:00:00+00:00"


@pytest.mark.asyncio
async def test_resolve_booking_request_reports_no_availability(db_session, monkeypatch):
    monday = _next_monday(date.today())
    _mock_parse(monkeypatch, earliest_date=str(monday), latest_date=str(monday))
    monkeypatch.setattr(
        booking_service._calendar_provider,
        "get_busy_blocks",
        AsyncMock(return_value=[BusyBlock(start=f"{monday}T09:00:00+00:00", end=f"{monday}T17:00:00+00:00")]),
    )

    result = await booking_service.resolve_booking_request(db_session, "book a consultation", "UTC", None)

    assert result.status == "no_availability"


@pytest.mark.asyncio
async def test_resolve_booking_request_degrades_to_clarification_on_malformed_llm_json(db_session, monkeypatch):
    fake_chat = AsyncMock(return_value=LLMResult(text="not valid json", usage=None))
    monkeypatch.setattr(booking_service._llm_client, "chat", fake_chat)

    result = await booking_service.resolve_booking_request(db_session, "book something", "UTC", None)

    assert result.status == "clarification_needed"
    assert result.clarification_question == booking_service.GENERIC_CLARIFICATION


@pytest.mark.asyncio
async def test_resolve_booking_request_degrades_to_clarification_when_llm_call_fails(db_session, monkeypatch):
    fake_chat = AsyncMock(side_effect=RuntimeError("boom"))
    monkeypatch.setattr(booking_service._llm_client, "chat", fake_chat)

    result = await booking_service.resolve_booking_request(db_session, "book something", "UTC", None)

    assert result.status == "clarification_needed"


@pytest.mark.asyncio
async def test_resolve_booking_request_not_configured_for_unknown_business(db_session):
    result = await booking_service.resolve_booking_request(
        db_session, "book something", "UTC", "00000000-0000-0000-0000-000000000000"
    )

    assert result.status == "not_configured"


@pytest.mark.asyncio
async def test_resolve_booking_request_propagates_calendar_error(db_session, monkeypatch):
    monday = _next_monday(date.today())
    _mock_parse(monkeypatch, earliest_date=str(monday), latest_date=str(monday))
    monkeypatch.setattr(
        booking_service._calendar_provider,
        "get_busy_blocks",
        AsyncMock(side_effect=GoogleCalendarError("boom")),
    )

    with pytest.raises(GoogleCalendarError):
        await booking_service.resolve_booking_request(db_session, "book a consultation", "UTC", None)


@pytest.mark.asyncio
async def test_confirm_booking_slot_books_and_persists(db_session, monkeypatch):
    monday = _next_monday(date.today())
    start = datetime.fromisoformat(f"{monday}T10:00:00+00:00")
    end = datetime.fromisoformat(f"{monday}T10:30:00+00:00")
    monkeypatch.setattr(booking_service._calendar_provider, "get_busy_blocks", AsyncMock(return_value=[]))
    fake_create_event = AsyncMock(return_value="event-xyz")
    monkeypatch.setattr(booking_service._calendar_provider, "create_event", fake_create_event)

    result = await booking_service.confirm_booking_slot(
        db_session, None, start, end, "UTC", "Jane Doe", "jane@example.com", None, "consultation", "sess-1"
    )

    assert result.status == "booked"
    assert result.event_id == "event-xyz"
    assert result.notify_email == settings.booking_notification_email
    booking = db_session.query(Booking).filter(Booking.calendar_event_id == "event-xyz").first()
    assert booking is not None
    assert booking.name == "Jane Doe"


@pytest.mark.asyncio
async def test_confirm_booking_slot_reports_conflict_on_overlap(db_session, monkeypatch):
    monday = _next_monday(date.today())
    start = datetime.fromisoformat(f"{monday}T10:00:00+00:00")
    end = datetime.fromisoformat(f"{monday}T10:30:00+00:00")
    monkeypatch.setattr(
        booking_service._calendar_provider,
        "get_busy_blocks",
        AsyncMock(return_value=[BusyBlock(start=f"{monday}T09:30:00+00:00", end=f"{monday}T10:15:00+00:00")]),
    )
    fake_create_event = AsyncMock()
    monkeypatch.setattr(booking_service._calendar_provider, "create_event", fake_create_event)

    result = await booking_service.confirm_booking_slot(
        db_session, None, start, end, "UTC", "Jane Doe", "jane@example.com", None, "consultation", None
    )

    assert result.status == "conflict"
    fake_create_event.assert_not_awaited()


@pytest.mark.asyncio
async def test_confirm_booking_slot_rejects_a_slot_in_the_past(db_session):
    past = datetime.fromisoformat("2020-01-01T10:00:00+00:00")

    result = await booking_service.confirm_booking_slot(
        db_session, None, past, past + timedelta(minutes=30), "UTC", "Jane", "jane@example.com", None, "call", None
    )

    assert result.status == "conflict"


@pytest.mark.asyncio
async def test_confirm_booking_slot_not_configured_for_unknown_business(db_session):
    monday = _next_monday(date.today())
    start = datetime.fromisoformat(f"{monday}T10:00:00+00:00")
    end = datetime.fromisoformat(f"{monday}T10:30:00+00:00")

    result = await booking_service.confirm_booking_slot(
        db_session,
        "00000000-0000-0000-0000-000000000000",
        start,
        end,
        "UTC",
        "Jane",
        "jane@example.com",
        None,
        "call",
        None,
    )

    assert result.status == "not_configured"
