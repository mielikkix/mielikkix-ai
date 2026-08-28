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
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.core.config import settings
from app.api import agents_booking
from app.integrations.google_calendar_client import BusyBlock, GoogleCalendarError
from app.models.booking import Booking
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
    monkeypatch.setattr(agents_booking._calendar_provider, "get_busy_blocks", fake_get_busy_blocks)

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
    monkeypatch.setattr(agents_booking._calendar_provider, "get_busy_blocks", AsyncMock(return_value=[]))

    resp = _get(start="2026-09-01", end="2026-09-02")

    assert resp.status_code == 200
    assert resp.json() == {"busy": []}


def test_calendar_error_surfaces_as_bad_gateway(monkeypatch):
    """GoogleCalendarError (missing credentials, or the upstream Google API
    itself failing) must come back as 502, not 500 -- this app is fine, the
    upstream dependency is what failed (see agents_booking.py's comment on
    this exact choice)."""
    monkeypatch.setattr(
        agents_booking._calendar_provider,
        "get_busy_blocks",
        AsyncMock(side_effect=GoogleCalendarError("Google Calendar isn't connected yet")),
    )

    resp = _get(start="2026-09-01", end="2026-09-02")

    assert resp.status_code == 502
    assert "isn't connected yet" in resp.json()["detail"]


def test_missing_required_query_params_is_unprocessable(monkeypatch):
    fake_get_busy_blocks = AsyncMock(return_value=[])
    monkeypatch.setattr(agents_booking._calendar_provider, "get_busy_blocks", fake_get_busy_blocks)

    resp = client.get("/api/agents/booking/dev/busy")

    assert resp.status_code == 422
    fake_get_busy_blocks.assert_not_awaited()


def test_timezone_defaults_to_utc_when_not_given(monkeypatch):
    fake_get_busy_blocks = AsyncMock(return_value=[])
    monkeypatch.setattr(agents_booking._calendar_provider, "get_busy_blocks", fake_get_busy_blocks)

    _get(start="2026-09-01", end="2026-09-02")

    fake_get_busy_blocks.assert_awaited_once_with(date(2026, 9, 1), date(2026, 9, 2), "UTC")


def test_custom_timezone_is_passed_through(monkeypatch):
    fake_get_busy_blocks = AsyncMock(return_value=[])
    monkeypatch.setattr(agents_booking._calendar_provider, "get_busy_blocks", fake_get_busy_blocks)

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
# Phase 2: POST /request -- free text in, open slots (or a clarifying
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
    return client.post("/api/agents/booking/request", json={"message": message})


def test_request_returns_open_slots_when_available(monkeypatch):
    monday = _next_monday(date.today())
    _mock_parse(monkeypatch, earliest_date=str(monday), latest_date=str(monday))
    monkeypatch.setattr(agents_booking._calendar_provider, "get_busy_blocks", AsyncMock(return_value=[]))

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
        agents_booking._calendar_provider,
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


def test_request_falls_back_to_clarification_when_the_llm_call_itself_fails(monkeypatch):
    """A real live failure this covers: groq.BadRequestError ("max
    completion tokens reached before generating a valid document") when a
    reasoning model spends its completion budget on internal reasoning
    before ever emitting JSON -- used to propagate straight past
    _parse_request as a raw 500 instead of degrading like a malformed
    response already did."""
    fake_chat = AsyncMock(side_effect=RuntimeError("boom"))
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
        agents_booking._calendar_provider, "get_busy_blocks", AsyncMock(side_effect=GoogleCalendarError("boom"))
    )

    resp = _request()

    assert resp.status_code == 502


def test_request_works_outside_debug_mode(monkeypatch):
    """Unlike /dev/busy, /request is public -- it's what the real chat
    widget and /demo/booking-assistant call in production, where DEBUG is
    off (see request_booking's own docstring on this)."""
    monkeypatch.setattr(settings, "debug", False)
    monday = _next_monday(date.today())
    _mock_parse(monkeypatch, earliest_date=str(monday), latest_date=str(monday))
    monkeypatch.setattr(agents_booking._calendar_provider, "get_busy_blocks", AsyncMock(return_value=[]))

    resp = _request()

    assert resp.status_code == 200
    assert resp.json()["status"] == "needs_selection"


# ---------------------------------------------------------------------------
# Phase 3: POST /confirm -- books one previously-offered slot, after
# re-checking it's still free, then persists a Booking row and fires a
# notification. get_busy_blocks/create_event are always mocked (no test
# creates a real Google Calendar event); confirm tests use the isolated
# `client`/`db_session` fixtures from conftest.py (unlike the plain
# module-level `client` above) since this route now writes to the database
# -- same reason test_agents_support.py uses those fixtures for Ticket rows.
# ---------------------------------------------------------------------------


def _confirm(client, **overrides):
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
    return client.post("/api/agents/booking/confirm", json=body)


def test_confirm_books_when_slot_is_still_free(client, db_session, monkeypatch):
    monkeypatch.setattr(agents_booking._calendar_provider, "get_busy_blocks", AsyncMock(return_value=[]))
    fake_create_event = AsyncMock(return_value="event-abc-123")
    monkeypatch.setattr(agents_booking._calendar_provider, "create_event", fake_create_event)
    fake_notify = AsyncMock()
    monkeypatch.setattr(agents_booking, "notify_new_booking", fake_notify)

    resp = _confirm(client)

    assert resp.status_code == 200
    assert resp.json() == {"status": "booked", "event_id": "event-abc-123"}
    fake_create_event.assert_awaited_once()
    kwargs = fake_create_event.await_args.kwargs
    assert kwargs["attendee_email"] == "jane@example.com"
    assert "Jane Doe" in kwargs["summary"]

    # Persisted (see agents_booking.confirm_booking's db.add/commit), not
    # just returned in the response -- this is what a future dashboard
    # "Bookings" view or Phase 4 handoff would read back.
    booking = db_session.query(Booking).filter(Booking.calendar_event_id == "event-abc-123").first()
    assert booking is not None
    assert booking.name == "Jane Doe"
    assert booking.email == "jane@example.com"
    assert booking.status == "confirmed"

    # The business gets notified too (Google's own invite already told the
    # customer) -- TestClient runs BackgroundTasks synchronously before
    # returning, so this has already fired by the time the response comes
    # back.
    fake_notify.assert_awaited_once()
    assert fake_notify.await_args.args[0] == settings.booking_notification_email
    assert fake_notify.await_args.args[1].calendar_event_id == "event-abc-123"


def test_confirm_reports_conflict_when_slot_was_taken_in_the_meantime(client, db_session, monkeypatch):
    monday = _next_monday(date.today())
    monkeypatch.setattr(
        agents_booking._calendar_provider,
        "get_busy_blocks",
        AsyncMock(return_value=[BusyBlock(start=f"{monday}T09:30:00+00:00", end=f"{monday}T10:15:00+00:00")]),
    )
    fake_create_event = AsyncMock()
    monkeypatch.setattr(agents_booking._calendar_provider, "create_event", fake_create_event)

    resp = _confirm(client)

    assert resp.json() == {"status": "conflict", "event_id": None}
    fake_create_event.assert_not_awaited()
    assert db_session.query(Booking).count() == 0


def test_confirm_rejects_a_slot_already_in_the_past(client, db_session, monkeypatch):
    fake_get_busy_blocks = AsyncMock(return_value=[])
    monkeypatch.setattr(agents_booking._calendar_provider, "get_busy_blocks", fake_get_busy_blocks)

    resp = _confirm(client, start="2020-01-01T10:00:00+00:00", end="2020-01-01T10:30:00+00:00")

    assert resp.json()["status"] == "conflict"
    fake_get_busy_blocks.assert_not_awaited()


def test_confirm_rejects_unparsable_datetimes(client):
    resp = _confirm(client, start="not-a-date", end="also-not-a-date")

    assert resp.status_code == 422


def test_confirm_surfaces_calendar_error_as_bad_gateway(client, monkeypatch):
    monkeypatch.setattr(
        agents_booking._calendar_provider, "get_busy_blocks", AsyncMock(side_effect=GoogleCalendarError("boom"))
    )

    resp = _confirm(client)

    assert resp.status_code == 502


def test_confirm_works_outside_debug_mode(client, db_session, monkeypatch):
    """Unlike /dev/busy, /confirm is public -- see confirm_booking's own
    docstring on why (it's what the real chat widget/demo page call)."""
    monkeypatch.setattr(settings, "debug", False)
    monkeypatch.setattr(agents_booking._calendar_provider, "get_busy_blocks", AsyncMock(return_value=[]))
    monkeypatch.setattr(agents_booking._calendar_provider, "create_event", AsyncMock(return_value="evt-1"))
    monkeypatch.setattr(agents_booking, "notify_new_booking", AsyncMock())

    resp = _confirm(client)

    assert resp.status_code == 200
    assert resp.json()["status"] == "booked"


# ---------------------------------------------------------------------------
# Phase 5: a real business_id resolves to THAT business's own connected
# calendar/hours instead of Mielikkix's demo one, via
# agents_booking._resolve_calendar_provider/_resolve_business_hours (see
# app/integrations/calendar_provider.py's get_calendar_provider). All of
# these use the isolated `client`/`db_session`/`business`/`set_plan`
# fixtures since they touch real CalendarConnection/BusinessSettings rows.
# The critical property under test throughout: a business with no working
# setup gets "not_configured", never a silent fallback to Mielikkix's own
# demo calendar (_calendar_provider) on that business's behalf.
# ---------------------------------------------------------------------------


def test_request_with_business_id_not_configured_when_plan_lacks_feature(client, business):
    # Free plan (business fixture's default) doesn't include booking_enabled.
    resp = client.post(
        "/api/agents/booking/request",
        json={"message": "book a call", "business_id": business["business_id"]},
    )

    assert resp.status_code == 200
    assert resp.json()["status"] == "not_configured"


def test_request_with_business_id_not_configured_when_no_connection(client, business, set_plan):
    set_plan(business["business_id"], "business")

    resp = client.post(
        "/api/agents/booking/request",
        json={"message": "book a call", "business_id": business["business_id"]},
    )

    assert resp.json()["status"] == "not_configured"


def test_request_with_unknown_business_id_not_configured(client):
    resp = client.post(
        "/api/agents/booking/request",
        json={"message": "book a call", "business_id": "00000000-0000-0000-0000-000000000000"},
    )

    assert resp.json()["status"] == "not_configured"


def test_request_with_business_id_not_configured_when_hours_unset(client, business, set_plan, db_session):
    from app.core.encryption import encrypt
    from app.models.calendar_connection import CalendarConnection

    set_plan(business["business_id"], "business")
    db_session.add(
        CalendarConnection(business_id=business["business_id"], refresh_token_encrypted=encrypt("tenant-token"))
    )
    db_session.commit()

    resp = client.post(
        "/api/agents/booking/request",
        json={"message": "book a call", "business_id": business["business_id"]},
    )

    assert resp.json()["status"] == "not_configured"


def test_request_with_business_id_skips_llm_call_when_not_configured(client, business, monkeypatch):
    fake_chat = _mock_parse(monkeypatch)

    client.post(
        "/api/agents/booking/request",
        json={"message": "book a call", "business_id": business["business_id"]},
    )

    fake_chat.assert_not_awaited()


def test_request_with_business_id_uses_tenant_calendar_and_hours(client, business, set_plan, db_session, monkeypatch):
    from app.core.encryption import encrypt
    from app.models.business import BusinessSettings
    from app.models.calendar_connection import CalendarConnection

    set_plan(business["business_id"], "business")
    db_session.add(
        CalendarConnection(business_id=business["business_id"], refresh_token_encrypted=encrypt("tenant-token"))
    )
    biz_settings = (
        db_session.query(BusinessSettings)
        .filter(BusinessSettings.business_id == business["business_id"])
        .first()
    )
    monday = _next_monday(date.today())
    # Tenant is open Mondays 9-17 -- deliberately different from the global
    # settings.booking_agent_hours_* window this test doesn't touch, so a
    # slot outside THAT global window still proves the tenant's own hours
    # were actually used, not a coincidental match.
    biz_settings.business_hours = {"monday": {"open": "09:00", "close": "17:00"}}
    db_session.commit()

    fake_provider = MagicMock()
    fake_provider.get_busy_blocks = AsyncMock(return_value=[])
    monkeypatch.setattr(agents_booking, "get_calendar_provider", lambda db, business_id: fake_provider)
    _mock_parse(monkeypatch, earliest_date=str(monday), latest_date=str(monday))

    resp = client.post(
        "/api/agents/booking/request",
        json={"message": "book a call", "business_id": business["business_id"]},
    )

    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "needs_selection"
    assert body["slots"][0]["start"] == f"{monday}T09:00:00+00:00"
    fake_provider.get_busy_blocks.assert_awaited_once()


def test_confirm_with_business_id_not_configured_when_no_connection(client, business, set_plan):
    set_plan(business["business_id"], "business")

    resp = _confirm(client, business_id=business["business_id"])

    assert resp.json()["status"] == "not_configured"


def test_confirm_with_business_id_books_via_tenant_calendar(client, business, set_plan, db_session, monkeypatch):
    from app.core.encryption import encrypt
    from app.models.calendar_connection import CalendarConnection

    set_plan(business["business_id"], "business")
    db_session.add(
        CalendarConnection(business_id=business["business_id"], refresh_token_encrypted=encrypt("tenant-token"))
    )
    db_session.commit()

    fake_provider = MagicMock()
    fake_provider.get_busy_blocks = AsyncMock(return_value=[])
    fake_provider.create_event = AsyncMock(return_value="tenant-event-id")
    monkeypatch.setattr(agents_booking, "get_calendar_provider", lambda db, business_id: fake_provider)
    # This business_id's own booking must never reach Mielikkix's demo
    # calendar -- fail loudly if anything still routes there.
    monkeypatch.setattr(
        agents_booking._calendar_provider, "create_event", AsyncMock(side_effect=AssertionError("wrong calendar"))
    )

    resp = _confirm(client, business_id=business["business_id"])

    assert resp.status_code == 200
    assert resp.json() == {"status": "booked", "event_id": "tenant-event-id"}
    fake_provider.create_event.assert_awaited_once()

    booking = db_session.query(Booking).filter(Booking.calendar_event_id == "tenant-event-id").first()
    assert booking is not None


def test_confirm_with_business_id_notifies_the_businesss_own_contact_email(
    client, business, set_plan, db_session, monkeypatch
):
    """A business_id-scoped booking must notify THAT business's own
    contact_email, never settings.booking_notification_email -- otherwise
    every real tenant's booking would silently tell Mielikkix about it
    instead of the tenant itself (confirmed live: exactly this happened
    before this fix -- Mielikkix's own inbox got a "New booking" email for
    a booking made through a real tenant's widget)."""
    from app.core.encryption import encrypt
    from app.models.business import BusinessSettings
    from app.models.calendar_connection import CalendarConnection

    set_plan(business["business_id"], "business")
    db_session.add(
        CalendarConnection(business_id=business["business_id"], refresh_token_encrypted=encrypt("tenant-token"))
    )
    biz_settings = (
        db_session.query(BusinessSettings)
        .filter(BusinessSettings.business_id == business["business_id"])
        .first()
    )
    biz_settings.contact_email = "owner@littlespaceforit.example"
    db_session.commit()

    fake_provider = MagicMock()
    fake_provider.get_busy_blocks = AsyncMock(return_value=[])
    fake_provider.create_event = AsyncMock(return_value="tenant-event-id")
    monkeypatch.setattr(agents_booking, "get_calendar_provider", lambda db, business_id: fake_provider)
    fake_notify = AsyncMock()
    monkeypatch.setattr(agents_booking, "notify_new_booking", fake_notify)

    resp = _confirm(client, business_id=business["business_id"])

    assert resp.status_code == 200
    fake_notify.assert_awaited_once()
    assert fake_notify.await_args.args[0] == "owner@littlespaceforit.example"
    assert fake_notify.await_args.args[0] != settings.booking_notification_email


def test_confirm_with_business_id_skips_notification_when_no_contact_email_on_file(
    client, business, set_plan, db_session, monkeypatch
):
    """No contact_email on file means no notification -- must never fall
    back to Mielikkix's own settings.booking_notification_email either.
    Registration defaults contact_email to the owner's own login email
    (see auth_service.register), so explicitly clear it here to exercise
    the "never got around to setting one" state this test is actually
    about."""
    from app.core.encryption import encrypt
    from app.models.business import BusinessSettings
    from app.models.calendar_connection import CalendarConnection

    set_plan(business["business_id"], "business")
    db_session.add(
        CalendarConnection(business_id=business["business_id"], refresh_token_encrypted=encrypt("tenant-token"))
    )
    db_session.query(BusinessSettings).filter(
        BusinessSettings.business_id == business["business_id"]
    ).update({"contact_email": None})
    db_session.commit()

    fake_provider = MagicMock()
    fake_provider.get_busy_blocks = AsyncMock(return_value=[])
    fake_provider.create_event = AsyncMock(return_value="tenant-event-id")
    monkeypatch.setattr(agents_booking, "get_calendar_provider", lambda db, business_id: fake_provider)
    fake_notify = AsyncMock()
    monkeypatch.setattr(agents_booking, "notify_new_booking", fake_notify)

    resp = _confirm(client, business_id=business["business_id"])

    assert resp.status_code == 200
    fake_notify.assert_not_awaited()
