"""
Booking Assistant -- Phase 1-3 tests (see apps/agents/booking-assistant/CLAUDE.md
and app/api/agents_booking.py's own module docstring for the phased plan).
Phase 1 is one route listing real busy blocks. Phase 2 turns a free-text
request into open slots (LLM mocked, same convention as
test_agents_support.py). Phase 3 books one of those slots (Google Calendar
client mocked). No test in this file makes a real Google Calendar or LLM
call.
"""

import json
from datetime import date, timedelta
from unittest.mock import AsyncMock

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.core.config import settings
from app.api import agents_booking
from app.integrations.google_calendar_client import BusyBlock, GoogleCalendarError
from mielikkix_agent_core import LLMResult

client = TestClient(app)


def _next_monday(after: date) -> date:
    """A Monday guaranteed to be at least a week after `after` -- computed
    from the real calendar rather than a hardcoded date, so these tests
    stay correct regardless of what day they're actually run on."""
    days_until_monday = (7 - after.weekday()) % 7 or 7
    return after + timedelta(days=days_until_monday + 7)


@pytest.fixture(autouse=True)
def _debug_mode(monkeypatch):
    """The /dev/busy route 404s outside settings.debug (see agents_booking.py's
    _require_debug) -- this module's whole point is exercising that route, so
    default every test in it to debug mode. The one test that cares about the
    opposite (production-mode 404) overrides this itself."""
    monkeypatch.setattr(settings, "debug", True)


def _get(**params):
    return client.get("/api/agents/booking/dev/busy", params=params)


def test_returns_busy_blocks_from_calendar(monkeypatch):
    fake_get_busy_blocks = AsyncMock(
        return_value=[
            BusyBlock(start="2026-09-01T09:00:00+00:00", end="2026-09-01T10:00:00+00:00"),
            BusyBlock(start="2026-09-01T14:00:00+00:00", end="2026-09-01T15:00:00+00:00"),
        ]
    )
    monkeypatch.setattr(agents_booking, "get_busy_blocks", fake_get_busy_blocks)

    resp = _get(start="2026-09-01", end="2026-09-02")

    assert resp.status_code == 200
    assert resp.json() == {
        "busy": [
            {"start": "2026-09-01T09:00:00+00:00", "end": "2026-09-01T10:00:00+00:00"},
            {"start": "2026-09-01T14:00:00+00:00", "end": "2026-09-01T15:00:00+00:00"},
        ]
    }
    fake_get_busy_blocks.assert_awaited_once()


def test_no_busy_blocks_returns_empty_list(monkeypatch):
    monkeypatch.setattr(agents_booking, "get_busy_blocks", AsyncMock(return_value=[]))

    resp = _get(start="2026-09-01", end="2026-09-02")

    assert resp.status_code == 200
    assert resp.json() == {"busy": []}


def test_calendar_error_surfaces_as_bad_gateway(monkeypatch):
    """GoogleCalendarError (missing credentials, or the upstream Google API
    itself failing) must come back as 502, not 500 -- this app is fine, the
    upstream dependency is what failed (see agents_booking.py's comment on
    this exact choice)."""
    monkeypatch.setattr(
        agents_booking,
        "get_busy_blocks",
        AsyncMock(side_effect=GoogleCalendarError("Google Calendar isn't connected yet")),
    )

    resp = _get(start="2026-09-01", end="2026-09-02")

    assert resp.status_code == 502
    assert "isn't connected yet" in resp.json()["detail"]


def test_missing_required_query_params_is_unprocessable(monkeypatch):
    fake_get_busy_blocks = AsyncMock(return_value=[])
    monkeypatch.setattr(agents_booking, "get_busy_blocks", fake_get_busy_blocks)

    resp = client.get("/api/agents/booking/dev/busy")

    assert resp.status_code == 422
    fake_get_busy_blocks.assert_not_awaited()


def test_timezone_defaults_to_utc_when_not_given(monkeypatch):
    fake_get_busy_blocks = AsyncMock(return_value=[])
    monkeypatch.setattr(agents_booking, "get_busy_blocks", fake_get_busy_blocks)

    _get(start="2026-09-01", end="2026-09-02")

    fake_get_busy_blocks.assert_awaited_once_with(date(2026, 9, 1), date(2026, 9, 2), "UTC")


def test_custom_timezone_is_passed_through(monkeypatch):
    fake_get_busy_blocks = AsyncMock(return_value=[])
    monkeypatch.setattr(agents_booking, "get_busy_blocks", fake_get_busy_blocks)

    _get(start="2026-09-01", end="2026-09-02", timezone="America/New_York")

    fake_get_busy_blocks.assert_awaited_once_with(date(2026, 9, 1), date(2026, 9, 2), "America/New_York")


def test_dev_route_404s_outside_debug_mode(monkeypatch):
    """Outside debug mode, /dev/busy must 404 (not 403 or reveal it exists at
    all to an outsider) -- see _require_debug's docstring on why 404
    specifically."""
    monkeypatch.setattr(settings, "debug", False)

    resp = _get(start="2026-09-01", end="2026-09-02")

    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# Phase 2: _available_slots_for_range -- pure function, no HTTP/mocking needed
# ---------------------------------------------------------------------------


class TestAvailableSlotsForRange:
    @pytest.fixture(autouse=True)
    def _business_hours(self, monkeypatch):
        monkeypatch.setattr(settings, "booking_agent_hours_start", "09:00")
        monkeypatch.setattr(settings, "booking_agent_hours_end", "17:00")

    def test_full_day_free_fills_business_hours(self):
        monday = _next_monday(date.today())

        slots = agents_booking._available_slots_for_range([], monday, monday, 60, "UTC")

        assert len(slots) == 8  # 09:00-17:00 in 1-hour slots
        assert slots[0][0].isoformat() == f"{monday}T09:00:00+00:00"
        assert slots[-1][1].isoformat() == f"{monday}T17:00:00+00:00"

    def test_busy_block_removes_overlapping_time(self):
        monday = _next_monday(date.today())
        busy = [BusyBlock(start=f"{monday}T09:00:00+00:00", end=f"{monday}T10:30:00+00:00")]

        slots = agents_booking._available_slots_for_range(busy, monday, monday, 30, "UTC")

        assert slots[0][0].isoformat() == f"{monday}T10:30:00+00:00"

    def test_busy_block_in_the_middle_splits_into_two_ranges(self):
        monday = _next_monday(date.today())
        busy = [BusyBlock(start=f"{monday}T12:00:00+00:00", end=f"{monday}T13:00:00+00:00")]

        slots = agents_booking._available_slots_for_range(busy, monday, monday, 180, "UTC")

        assert [(s.isoformat(), e.isoformat()) for s, e in slots] == [
            (f"{monday}T09:00:00+00:00", f"{monday}T12:00:00+00:00"),
            (f"{monday}T13:00:00+00:00", f"{monday}T16:00:00+00:00"),
        ]

    def test_weekend_only_range_has_no_slots(self):
        monday = _next_monday(date.today())
        saturday, sunday = monday + timedelta(days=5), monday + timedelta(days=6)

        slots = agents_booking._available_slots_for_range([], saturday, sunday, 30, "UTC")

        assert slots == []

    def test_result_is_capped_at_max_slots_returned(self):
        monday = _next_monday(date.today())

        slots = agents_booking._available_slots_for_range([], monday, monday, 15, "UTC")

        assert len(slots) == agents_booking._MAX_SLOTS_RETURNED


# ---------------------------------------------------------------------------
# Phase 2: POST /dev/request -- free text in, open slots (or a clarifying
# question) out. The LLM call is always mocked, same convention
# test_agents_support.py uses for its own classification call.
# ---------------------------------------------------------------------------


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
    monkeypatch.setattr(agents_booking._llm_client, "chat", fake_chat)
    return fake_chat


def _request(message="I'd like a 30 minute consultation"):
    return client.post("/api/agents/booking/dev/request", json={"message": message})


def test_request_returns_open_slots_when_available(monkeypatch):
    monday = _next_monday(date.today())
    _mock_parse(monkeypatch, earliest_date=str(monday), latest_date=str(monday))
    monkeypatch.setattr(agents_booking, "get_busy_blocks", AsyncMock(return_value=[]))

    resp = _request()

    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "needs_selection"
    assert body["meeting_type"] == "consultation"
    assert body["duration_minutes"] == 30
    assert len(body["slots"]) > 0
    assert body["slots"][0]["start"] == f"{monday}T09:00:00+00:00"


def test_request_reports_no_availability_for_a_fully_booked_range(monkeypatch):
    monday = _next_monday(date.today())
    _mock_parse(monkeypatch, earliest_date=str(monday), latest_date=str(monday))
    monkeypatch.setattr(
        agents_booking,
        "get_busy_blocks",
        AsyncMock(return_value=[BusyBlock(start=f"{monday}T09:00:00+00:00", end=f"{monday}T17:00:00+00:00")]),
    )

    resp = _request()

    assert resp.json()["status"] == "no_availability"


def test_request_asks_for_clarification_when_llm_says_so(monkeypatch):
    _mock_parse(
        monkeypatch,
        clarification_needed=True,
        clarification_question="What day works for you?",
    )

    resp = _request(message="I want to book something")

    body = resp.json()
    assert body["status"] == "clarification_needed"
    assert body["clarification_question"] == "What day works for you?"


def test_request_falls_back_to_clarification_on_malformed_llm_json(monkeypatch):
    fake_chat = AsyncMock(return_value=LLMResult(text="not valid json", usage=None))
    monkeypatch.setattr(agents_booking._llm_client, "chat", fake_chat)

    resp = _request()

    assert resp.status_code == 200
    assert resp.json()["status"] == "clarification_needed"


def test_request_falls_back_to_clarification_when_dates_are_backwards(monkeypatch):
    monday = _next_monday(date.today())
    _mock_parse(monkeypatch, earliest_date=str(monday), latest_date=str(monday - timedelta(days=1)))

    resp = _request()

    assert resp.json()["status"] == "clarification_needed"


def test_request_surfaces_calendar_error_as_bad_gateway(monkeypatch):
    monday = _next_monday(date.today())
    _mock_parse(monkeypatch, earliest_date=str(monday), latest_date=str(monday))
    monkeypatch.setattr(
        agents_booking, "get_busy_blocks", AsyncMock(side_effect=GoogleCalendarError("boom"))
    )

    resp = _request()

    assert resp.status_code == 502


def test_request_404s_outside_debug_mode(monkeypatch):
    monkeypatch.setattr(settings, "debug", False)

    resp = _request()

    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# Phase 3: POST /dev/confirm -- books one previously-offered slot, after
# re-checking it's still free. get_busy_blocks and create_event are always
# mocked here -- no test creates a real Google Calendar event.
# ---------------------------------------------------------------------------


def _confirm(**overrides):
    monday = _next_monday(date.today())
    body = {
        "name": "Jane Doe",
        "email": "jane@example.com",
        "phone": None,
        "start": f"{monday}T10:00:00+00:00",
        "end": f"{monday}T10:30:00+00:00",
        "timezone": "UTC",
        "meeting_type": "consultation",
    }
    body.update(overrides)
    return client.post("/api/agents/booking/dev/confirm", json=body)


def test_confirm_books_when_slot_is_still_free(monkeypatch):
    monkeypatch.setattr(agents_booking, "get_busy_blocks", AsyncMock(return_value=[]))
    fake_create_event = AsyncMock(return_value="event-abc-123")
    monkeypatch.setattr(agents_booking, "create_event", fake_create_event)

    resp = _confirm()

    assert resp.status_code == 200
    assert resp.json() == {"status": "booked", "event_id": "event-abc-123"}
    fake_create_event.assert_awaited_once()
    kwargs = fake_create_event.await_args.kwargs
    assert kwargs["attendee_email"] == "jane@example.com"
    assert "Jane Doe" in kwargs["summary"]


def test_confirm_reports_conflict_when_slot_was_taken_in_the_meantime(monkeypatch):
    monday = _next_monday(date.today())
    monkeypatch.setattr(
        agents_booking,
        "get_busy_blocks",
        AsyncMock(return_value=[BusyBlock(start=f"{monday}T09:30:00+00:00", end=f"{monday}T10:15:00+00:00")]),
    )
    fake_create_event = AsyncMock()
    monkeypatch.setattr(agents_booking, "create_event", fake_create_event)

    resp = _confirm()

    assert resp.json() == {"status": "conflict", "event_id": None}
    fake_create_event.assert_not_awaited()


def test_confirm_rejects_a_slot_already_in_the_past(monkeypatch):
    fake_get_busy_blocks = AsyncMock(return_value=[])
    monkeypatch.setattr(agents_booking, "get_busy_blocks", fake_get_busy_blocks)

    resp = _confirm(start="2020-01-01T10:00:00+00:00", end="2020-01-01T10:30:00+00:00")

    assert resp.json()["status"] == "conflict"
    fake_get_busy_blocks.assert_not_awaited()


def test_confirm_rejects_unparsable_datetimes():
    resp = _confirm(start="not-a-date", end="also-not-a-date")

    assert resp.status_code == 422


def test_confirm_surfaces_calendar_error_as_bad_gateway(monkeypatch):
    monkeypatch.setattr(
        agents_booking, "get_busy_blocks", AsyncMock(side_effect=GoogleCalendarError("boom"))
    )

    resp = _confirm()

    assert resp.status_code == 502


def test_confirm_404s_outside_debug_mode(monkeypatch):
    monkeypatch.setattr(settings, "debug", False)

    resp = _confirm()

    assert resp.status_code == 404
