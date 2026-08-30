"""
Per apps/agents/booking-assistant/CLAUDE.md's Phase 7 testing expectations:
"the Google Calendar client against a mocked API" -- no real Google account
or network call happens here. Two things get mocked at the boundary:

1. `Credentials.refresh` -- normally makes a real HTTPS call to Google's
   token endpoint to mint an access token from the refresh token. Replaced
   with a no-op so tests never need real OAuth credentials.
2. `requests.post` -- normally makes a real HTTP call to the Calendar REST
   API (freeBusy.query / events.insert). Replaced with a fake that records
   what was sent and returns a canned JSON response, the same "mock at the
   boundary" approach test_calcom_client.py used for httpx.

NOT `googleapiclient.discovery.build` -- this module calls the Calendar
REST API directly via `requests` rather than through googleapiclient's
httplib2 transport (see google_calendar_client.py's own comment on why:
httplib2 couldn't complete a TCP connection at all on the dev machine this
was diagnosed on, confirmed live via a raw httplib2 call hanging its full
timeout, while `requests` reached the same host in under a second).
"""

from datetime import date, datetime, timezone

import pytest
import requests

from app.integrations import google_calendar_client
from app.integrations.google_calendar_client import GoogleCalendarError, GoogleCalendarProvider


class _FakeResponse:
    def __init__(self, json_data: dict, status_code: int = 200):
        self._json_data = json_data
        self.status_code = status_code

    def raise_for_status(self):
        if self.status_code >= 400:
            raise requests.HTTPError(f"{self.status_code} error", response=self)

    def json(self):
        return self._json_data


class _FakePost:
    """Records the last call made through it -- mirrors the old
    _FakeService's last_query_body/last_insert_kwargs so assertions read
    the same way, just against requests.post's own kwargs instead of a
    googleapiclient method chain."""

    def __init__(self, response_json: dict, status_code: int = 200):
        self.response_json = response_json
        self.status_code = status_code
        self.last_url = None
        self.last_kwargs = None

    def __call__(self, url, **kwargs):
        self.last_url = url
        self.last_kwargs = kwargs
        return _FakeResponse(self.response_json, self.status_code)


def _configure_credentials(monkeypatch) -> GoogleCalendarProvider:
    """Returns a fresh GoogleCalendarProvider constructed AFTER patching
    settings -- __init__ now captures client_id/secret/refresh_token/
    calendar_id at construction time (so a real per-business connection's
    credentials aren't re-read on every call), which means a provider must
    be built fresh per test rather than shared at module scope, unlike
    before this class took constructor arguments."""
    monkeypatch.setattr(google_calendar_client.settings, "google_calendar_client_id", "test-client-id")
    monkeypatch.setattr(google_calendar_client.settings, "google_calendar_client_secret", "test-client-secret")
    monkeypatch.setattr(google_calendar_client.settings, "google_calendar_refresh_token", "test-refresh-token")
    monkeypatch.setattr(google_calendar_client.settings, "google_calendar_id", "primary")
    # Skip the real network call refresh() would otherwise make to Google's
    # token endpoint -- nothing here asserts on the resulting access token,
    # only on what get_busy_blocks/create_event does with the (mocked) API
    # response.
    monkeypatch.setattr(google_calendar_client.Credentials, "refresh", lambda self, request: None)
    return GoogleCalendarProvider()


def _patch_post(monkeypatch, response_json: dict, status_code: int = 200) -> _FakePost:
    fake_post = _FakePost(response_json, status_code)
    monkeypatch.setattr(google_calendar_client.requests, "post", fake_post)
    return fake_post


@pytest.mark.asyncio
async def test_get_busy_blocks_parses_response(monkeypatch):
    provider = _configure_credentials(monkeypatch)
    _patch_post(
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

    blocks = await provider.get_busy_blocks(date(2024, 8, 13), date(2024, 8, 14))

    assert [(b.start, b.end) for b in blocks] == [
        ("2024-08-13T09:00:00Z", "2024-08-13T10:00:00Z"),
        ("2024-08-14T14:00:00Z", "2024-08-14T15:30:00Z"),
    ]


@pytest.mark.asyncio
async def test_get_busy_blocks_sends_correct_query_body(monkeypatch):
    provider = _configure_credentials(monkeypatch)
    fake_post = _patch_post(monkeypatch, {"calendars": {"primary": {"busy": []}}})

    await provider.get_busy_blocks(date(2024, 8, 13), date(2024, 8, 14), timezone="America/New_York")

    assert fake_post.last_url == "https://www.googleapis.com/calendar/v3/freeBusy"
    sent_body = fake_post.last_kwargs["json"]
    # Must carry a real UTC offset, not a bare timestamp -- Google's API
    # rejects timeMin/timeMax without one (see google_calendar_client.py's
    # comment on this). August in America/New_York is EDT, UTC-4.
    assert sent_body["timeMin"] == "2024-08-13T00:00:00-04:00"
    assert sent_body["timeMax"] == "2024-08-14T23:59:59-04:00"
    assert sent_body["timeZone"] == "America/New_York"
    assert sent_body["items"] == [{"id": "primary"}]
    assert "Bearer" in fake_post.last_kwargs["headers"]["Authorization"]


@pytest.mark.asyncio
async def test_get_busy_blocks_returns_empty_list_when_calendar_has_no_busy_key(monkeypatch):
    provider = _configure_credentials(monkeypatch)
    _patch_post(monkeypatch, {"calendars": {"primary": {}}})

    blocks = await provider.get_busy_blocks(date(2024, 8, 13), date(2024, 8, 14))

    assert blocks == []


@pytest.mark.asyncio
async def test_get_busy_blocks_raises_when_not_configured(monkeypatch):
    monkeypatch.setattr(google_calendar_client.settings, "google_calendar_client_id", "")
    monkeypatch.setattr(google_calendar_client.settings, "google_calendar_client_secret", "")
    monkeypatch.setattr(google_calendar_client.settings, "google_calendar_refresh_token", "")
    provider = GoogleCalendarProvider()

    with pytest.raises(GoogleCalendarError, match="isn't connected yet"):
        await provider.get_busy_blocks(date(2024, 8, 13), date(2024, 8, 14))


@pytest.mark.asyncio
async def test_get_busy_blocks_raises_google_calendar_error_on_api_error(monkeypatch):
    provider = _configure_credentials(monkeypatch)
    _patch_post(monkeypatch, {"error": {"code": 403, "message": "insufficient scope"}}, status_code=403)

    with pytest.raises(GoogleCalendarError, match="freebusy query failed"):
        await provider.get_busy_blocks(date(2024, 8, 13), date(2024, 8, 14))


@pytest.mark.asyncio
async def test_create_event_returns_the_new_event_id(monkeypatch):
    provider = _configure_credentials(monkeypatch)
    _patch_post(monkeypatch, {"id": "real-event-id-123"})

    event_id = await provider.create_event(
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
    provider = _configure_credentials(monkeypatch)
    fake_post = _patch_post(monkeypatch, {"id": "fake-event-id"})

    await provider.create_event(
        summary="Consultation with Jane Doe",
        start=datetime(2024, 8, 13, 14, 0, tzinfo=timezone.utc),
        end=datetime(2024, 8, 13, 14, 30, tzinfo=timezone.utc),
        timezone="UTC",
        attendee_email="jane@example.com",
        description="Notes here.",
    )

    # sendUpdates="all" is what makes Google actually email the invite to
    # the attendee -- silently dropping this would mean a "booked"
    # response with no confirmation email ever sent, a real regression
    # this test exists to catch.
    assert fake_post.last_kwargs["params"] == {"sendUpdates": "all"}
    assert fake_post.last_url == "https://www.googleapis.com/calendar/v3/calendars/primary/events"
    body = fake_post.last_kwargs["json"]
    assert body["attendees"] == [{"email": "jane@example.com"}]
    assert body["summary"] == "Consultation with Jane Doe"
    assert body["start"] == {"dateTime": "2024-08-13T14:00:00+00:00", "timeZone": "UTC"}
    assert body["end"] == {"dateTime": "2024-08-13T14:30:00+00:00", "timeZone": "UTC"}


@pytest.mark.asyncio
async def test_provider_uses_explicit_credentials_over_global_settings(monkeypatch):
    """A per-business connection (see calendar_provider.get_calendar_provider)
    passes its own client_id/secret/refresh_token/calendar_id explicitly --
    confirms those win over whatever's in global settings, which is what
    makes per-tenant calendars actually isolated from Mielikkix's own demo
    one and from each other."""
    monkeypatch.setattr(google_calendar_client.settings, "google_calendar_client_id", "global-client-id")
    monkeypatch.setattr(google_calendar_client.settings, "google_calendar_client_secret", "global-secret")
    monkeypatch.setattr(google_calendar_client.settings, "google_calendar_refresh_token", "global-refresh-token")
    monkeypatch.setattr(google_calendar_client.settings, "google_calendar_id", "primary")
    monkeypatch.setattr(google_calendar_client.Credentials, "refresh", lambda self, request: None)
    fake_post = _patch_post(monkeypatch, {"calendars": {"tenant-calendar@example.com": {"busy": []}}})

    provider = GoogleCalendarProvider(
        client_id="tenant-client-id",
        client_secret="tenant-secret",
        refresh_token="tenant-refresh-token",
        calendar_id="tenant-calendar@example.com",
    )
    await provider.get_busy_blocks(date(2024, 8, 13), date(2024, 8, 14))

    sent_body = fake_post.last_kwargs["json"]
    assert sent_body["items"] == [{"id": "tenant-calendar@example.com"}]


@pytest.mark.asyncio
async def test_create_event_raises_google_calendar_error_on_api_error(monkeypatch):
    provider = _configure_credentials(monkeypatch)
    _patch_post(monkeypatch, {"error": {"code": 409, "message": "already booked"}}, status_code=409)

    with pytest.raises(GoogleCalendarError, match="event creation failed"):
        await provider.create_event(
            summary="x",
            start=datetime(2024, 8, 13, 14, 0, tzinfo=timezone.utc),
            end=datetime(2024, 8, 13, 14, 30, tzinfo=timezone.utc),
            timezone="UTC",
            attendee_email="jane@example.com",
        )


@pytest.mark.asyncio
async def test_get_busy_blocks_times_out_fast_instead_of_hanging(monkeypatch):
    """The whole reason _bounded/asyncio.wait_for wraps every real call
    here (see google_calendar_client.py's own comment) -- a network that
    never responds must fail within _CALENDAR_CALL_TIMEOUT_SECONDS, not
    hang for however long the OS's own TCP timeout happens to be."""
    provider = _configure_credentials(monkeypatch)
    monkeypatch.setattr(google_calendar_client, "_CALENDAR_CALL_TIMEOUT_SECONDS", 0.05)

    def _never_returns(url, **kwargs):
        # Long enough to prove wait_for's 0.05s timeout actually fires
        # before this returns, short enough not to hold up the test
        # process's own thread-pool teardown (asyncio.to_thread can't
        # cancel this once started -- see _bounded's own comment).
        import time

        time.sleep(0.5)

    monkeypatch.setattr(google_calendar_client.requests, "post", _never_returns)

    with pytest.raises(GoogleCalendarError, match="didn't respond"):
        await provider.get_busy_blocks(date(2024, 8, 13), date(2024, 8, 14))
