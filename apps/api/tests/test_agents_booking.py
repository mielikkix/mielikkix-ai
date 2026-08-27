"""
Booking Assistant -- Phase 1 tests (see apps/agents/booking-assistant/CLAUDE.md
and app/api/agents_booking.py's own module docstring for the phased plan).
Phase 1 is exactly one route: list a real Google Calendar's busy blocks for a
date range. get_busy_blocks is always mocked here (same convention as
test_agents_support.py and test_agents_voice.py) -- no test makes a real
Google Calendar API call.
"""

from datetime import date
from unittest.mock import AsyncMock

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.core.config import settings
from app.api import agents_booking
from app.integrations.google_calendar_client import BusyBlock, GoogleCalendarError

client = TestClient(app)


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
