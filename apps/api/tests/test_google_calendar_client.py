"""
Per apps/agents/booking-assistant/CLAUDE.md's Phase 7 testing expectations:
"the Google Calendar client against a mocked API" -- no real Google account
or network call happens here. Two things get mocked at the boundary:

1. `Credentials.refresh` -- normally makes a real HTTPS call to Google's
   token endpoint to mint an access token from the refresh token. Replaced
   with a no-op so tests never need real OAuth credentials.
2. `googleapiclient.discovery.build` -- normally builds a real HTTP-backed
   service object. Replaced with a fake whose `.freebusy().query(...).execute()`
   chain returns a canned response, the same "mock at the boundary"
   approach test_calcom_client.py used for httpx.
"""

from datetime import date, datetime, timezone

import pytest

from app.integrations import google_calendar_client
from app.integrations.google_calendar_client import GoogleCalendarError, create_event, get_busy_blocks


class _FakeFreebusy:
    def __init__(self, response: dict):
        self._response = response
        self.last_query_body = None

    def query(self, body):
        self.last_query_body = body
        return self

    def execute(self):
        return self._response


class _FakeEvents:
    def __init__(self, created_event: dict):
        self._created_event = created_event
        self.last_insert_kwargs = None

    def insert(self, **kwargs):
        self.last_insert_kwargs = kwargs
        return self

    def execute(self):
        return self._created_event


class _FakeService:
    def __init__(self, response: dict, created_event: dict | None = None):
        self._freebusy = _FakeFreebusy(response)
        self._events = _FakeEvents(created_event or {"id": "fake-event-id"})

    def freebusy(self):
        return self._freebusy

    def events(self):
        return self._events


def _configure_credentials(monkeypatch):
    monkeypatch.setattr(google_calendar_client.settings, "google_calendar_client_id", "test-client-id")
    monkeypatch.setattr(google_calendar_client.settings, "google_calendar_client_secret", "test-client-secret")
    monkeypatch.setattr(google_calendar_client.settings, "google_calendar_refresh_token", "test-refresh-token")
    monkeypatch.setattr(google_calendar_client.settings, "google_calendar_id", "primary")
    # Skip the real network call refresh() would otherwise make to Google's
    # token endpoint -- nothing here asserts on the resulting access token,
    # only on what get_busy_blocks does with the (mocked) API response.
    monkeypatch.setattr(google_calendar_client.Credentials, "refresh", lambda self, request: None)


def _patch_service(monkeypatch, response: dict) -> _FakeService:
    fake_service = _FakeService(response)
    monkeypatch.setattr(google_calendar_client, "build", lambda *args, **kwargs: fake_service)
    return fake_service


@pytest.mark.asyncio
async def test_get_busy_blocks_parses_response(monkeypatch):
    _configure_credentials(monkeypatch)
    _patch_service(
        monkeypatch,
        {
            "calendars": {
                "primary": {
                    "busy": [
                        {"start": "2024-08-13T09:00:00Z", "end": "2024-08-13T10:00:00Z"},
                        {"start": "2024-08-14T14:00:00Z", "end": "2024-08-14T15:30:00Z"},
                    ]
                }
            }
        },
    )

    blocks = await get_busy_blocks(date(2024, 8, 13), date(2024, 8, 14))

    assert [(b.start, b.end) for b in blocks] == [
        ("2024-08-13T09:00:00Z", "2024-08-13T10:00:00Z"),
        ("2024-08-14T14:00:00Z", "2024-08-14T15:30:00Z"),
    ]


@pytest.mark.asyncio
async def test_get_busy_blocks_sends_correct_query_body(monkeypatch):
    _configure_credentials(monkeypatch)
    fake_service = _patch_service(monkeypatch, {"calendars": {"primary": {"busy": []}}})

    await get_busy_blocks(date(2024, 8, 13), date(2024, 8, 14), timezone="America/New_York")

    sent_body = fake_service.freebusy().last_query_body
    # Must carry a real UTC offset, not a bare timestamp -- Google's API
    # rejects timeMin/timeMax without one (see google_calendar_client.py's
    # comment on this). August in America/New_York is EDT, UTC-4.
    assert sent_body["timeMin"] == "2024-08-13T00:00:00-04:00"
    assert sent_body["timeMax"] == "2024-08-14T23:59:59-04:00"
    assert sent_body["timeZone"] == "America/New_York"
    assert sent_body["items"] == [{"id": "primary"}]


@pytest.mark.asyncio
async def test_get_busy_blocks_returns_empty_list_when_calendar_has_no_busy_key(monkeypatch):
    _configure_credentials(monkeypatch)
    _patch_service(monkeypatch, {"calendars": {"primary": {}}})

    blocks = await get_busy_blocks(date(2024, 8, 13), date(2024, 8, 14))

    assert blocks == []


@pytest.mark.asyncio
async def test_get_busy_blocks_raises_when_not_configured(monkeypatch):
    monkeypatch.setattr(google_calendar_client.settings, "google_calendar_client_id", "")
    monkeypatch.setattr(google_calendar_client.settings, "google_calendar_client_secret", "")
    monkeypatch.setattr(google_calendar_client.settings, "google_calendar_refresh_token", "")

    with pytest.raises(GoogleCalendarError, match="isn't connected yet"):
        await get_busy_blocks(date(2024, 8, 13), date(2024, 8, 14))


@pytest.mark.asyncio
async def test_get_busy_blocks_raises_google_calendar_error_on_api_error(monkeypatch):
    _configure_credentials(monkeypatch)

    class _FailingFreebusy:
        def query(self, body):
            return self

        def execute(self):
            # HttpError's real constructor wants a urllib3/httplib2 response
            # object -- a plain Exception subclassing it well enough for
            # this test isn't worth the ceremony, so this simulates the
            # *effect* (get_busy_blocks_sync's except clause catching an
            # HttpError) by raising the real class with a minimal stand-in.
            from types import SimpleNamespace

            from googleapiclient.errors import HttpError

            raise HttpError(SimpleNamespace(status=403, reason="Forbidden"), b"insufficient scope")

    class _FailingService:
        def freebusy(self):
            return _FailingFreebusy()

    monkeypatch.setattr(google_calendar_client, "build", lambda *args, **kwargs: _FailingService())

    with pytest.raises(GoogleCalendarError, match="freebusy query failed"):
        await get_busy_blocks(date(2024, 8, 13), date(2024, 8, 14))


@pytest.mark.asyncio
async def test_create_event_returns_the_new_event_id(monkeypatch):
    _configure_credentials(monkeypatch)
    fake_service = _patch_service(monkeypatch, {"calendars": {"primary": {"busy": []}}})
    fake_service._events = _FakeEvents({"id": "real-event-id-123"})

    event_id = await create_event(
        summary="Consultation with Jane Doe",
        start=datetime(2024, 8, 13, 14, 0, tzinfo=timezone.utc),
        end=datetime(2024, 8, 13, 14, 30, tzinfo=timezone.utc),
        timezone="UTC",
        attendee_email="jane@example.com",
        description="Booked via Mielikkix Booking Assistant.",
    )

    assert event_id == "real-event-id-123"


@pytest.mark.asyncio
async def test_create_event_sends_attendee_and_sends_updates(monkeypatch):
    _configure_credentials(monkeypatch)
    fake_service = _patch_service(monkeypatch, {"calendars": {"primary": {"busy": []}}})

    await create_event(
        summary="Consultation with Jane Doe",
        start=datetime(2024, 8, 13, 14, 0, tzinfo=timezone.utc),
        end=datetime(2024, 8, 13, 14, 30, tzinfo=timezone.utc),
        timezone="UTC",
        attendee_email="jane@example.com",
        description="Notes here.",
    )

    sent = fake_service._events.last_insert_kwargs
    # sendUpdates="all" is what makes Google actually email the invite to
    # the attendee -- silently dropping this would mean a "booked"
    # response with no confirmation email ever sent, a real regression
    # this test exists to catch.
    assert sent["sendUpdates"] == "all"
    assert sent["calendarId"] == "primary"
    assert sent["body"]["attendees"] == [{"email": "jane@example.com"}]
    assert sent["body"]["summary"] == "Consultation with Jane Doe"
    assert sent["body"]["start"] == {"dateTime": "2024-08-13T14:00:00+00:00", "timeZone": "UTC"}
    assert sent["body"]["end"] == {"dateTime": "2024-08-13T14:30:00+00:00", "timeZone": "UTC"}


@pytest.mark.asyncio
async def test_create_event_raises_google_calendar_error_on_api_error(monkeypatch):
    _configure_credentials(monkeypatch)

    class _FailingEvents:
        def insert(self, **kwargs):
            return self

        def execute(self):
            from types import SimpleNamespace

            from googleapiclient.errors import HttpError

            raise HttpError(SimpleNamespace(status=409, reason="Conflict"), b"already booked")

    class _FailingService:
        def events(self):
            return _FailingEvents()

    monkeypatch.setattr(google_calendar_client, "build", lambda *args, **kwargs: _FailingService())

    with pytest.raises(GoogleCalendarError, match="event creation failed"):
        await create_event(
            summary="x",
            start=datetime(2024, 8, 13, 14, 0, tzinfo=timezone.utc),
            end=datetime(2024, 8, 13, 14, 30, tzinfo=timezone.utc),
            timezone="UTC",
            attendee_email="jane@example.com",
        )
