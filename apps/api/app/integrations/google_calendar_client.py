"""
Thin wrapper around the Google Calendar API v3 -- see
apps/agents/booking-assistant/CLAUDE.md for why Booking Assistant talks to
Google Calendar directly instead of running a separate scheduling engine
(the original plan was Cal.com, self-hosted; reversed after actually trying
it -- see that CLAUDE.md's "Why Google Calendar directly" section), and
apps/agents/CLAUDE.md for why this file lives in apps/api rather than
apps/agents/booking-assistant (same reason as app/api/agents_voice.py's own
module docstring: apps/api is the one running "shared modular agent
process").

Python note for a reader new to async Python, coming from Angular/TS: the
official Google API client (`googleapiclient`) is **synchronous** (it makes
a real blocking network call), unlike agent-core's LLMClient or Cal.com's
would-have-been httpx client. Calling it from an `async def` FastAPI route
would block the whole event loop for however long Google takes to respond
-- so every function here runs the actual Google call inside
`asyncio.to_thread(...)`, which hands it off to a background thread and lets
the rest of the app keep serving other requests meanwhile. This is the
Python equivalent of not wanting a synchronous XHR to freeze a browser tab.

OAuth note: this module only ever REFRESHES an already-obtained token
(settings.google_calendar_refresh_token) -- it never runs the interactive
"sign in with Google" consent flow itself. That's a separate, one-time,
human-in-the-browser step: scripts/connect_google_calendar.py for Phase 1's
one hardcoded test calendar, and (Phase 5) a real per-tenant OAuth flow in
the dashboard. Both produce the same kind of refresh token this module
consumes -- Phase 5 will pass a per-tenant refresh token in here instead of
always reading settings.google_calendar_refresh_token, but the token-
refresh/API-call mechanics below don't change.
"""

import asyncio
import socket
from datetime import date, datetime, time
from zoneinfo import ZoneInfo

import requests
import urllib3.util.connection as _urllib3_connection
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials

from ..core.config import settings
from .calendar_provider import BusyBlock, CalendarProvider

# Confirmed live on this dev machine: googleapis.com resolves an AAAA
# (IPv6) record, and this machine's IPv6 route to it is entirely dead (100%
# packet loss on a raw ping) -- but IPv4 works fine. `requests`/urllib3
# tries whichever address family DNS/getaddrinfo hands it first and only
# falls back after that connection attempt's own OS-level timeout (~20s on
# Windows), rather than racing both like curl effectively does -- so every
# single Google API call here was paying a ~20s tax before ever reaching a
# working address. Forcing IPv4-only resolution sidesteps the dead route
# entirely instead of just waiting it out faster. This mutates a shared
# urllib3 global, so it's process-wide, not scoped to this module's own
# calls -- safe regardless, since curl already proved IPv4 reaches every
# host this app talks to, and this module is the only one that actually
# routes through `requests`/urllib3 today (LLM calls go through httpx,
# which has its own separate transport and isn't affected either way).
_urllib3_connection.allowed_gai_family = lambda: socket.AF_INET

# Two narrow scopes, not the broad "calendar" (full read/write on
# everything) or "calendar.readonly" (would block booking) scopes:
#   - calendar.freebusy: read-only free/busy status. calendar.events does
#     NOT cover freebusy.query -- confirmed the hard way (a live 403
#     "Request had insufficient authentication scopes" from Google's own
#     API), not just from reading Google's scope docs; freebusy.query
#     specifically needs .freebusy, .readonly, or the full "calendar" scope,
#     .events isn't enough even though it sounds calendar-data-adjacent.
#   - calendar.events: create/manage events this agent creates. Doesn't
#     cover freebusy.query itself, but Phase 3 (booking creation) needs it.
# Must exactly match the scopes requested when the refresh token was
# obtained (see scripts/connect_google_calendar.py) -- Google rejects an
# API call made with a token that was never granted a scope it needs.
CALENDAR_SCOPES = [
    "https://www.googleapis.com/auth/calendar.freebusy",
    "https://www.googleapis.com/auth/calendar.events",
]


class GoogleCalendarError(Exception):
    """Raised when the Google Calendar API returns an error, or this
    module's credentials aren't configured yet. Callers decide their own
    fallback (e.g. "sorry, I couldn't check availability right now") rather
    than this module swallowing the failure silently -- same convention as
    calcom_client.py's CalComError before it."""


def _build_credentials(client_id: str, client_secret: str, refresh_token: str) -> Credentials:
    if not (client_id and client_secret and refresh_token):
        raise GoogleCalendarError(
            "Google Calendar isn't connected yet -- run "
            "scripts/connect_google_calendar.py and set the three "
            "GOOGLE_CALENDAR_* values it prints in your .env."
        )

    # Credentials built from a refresh token, no access token supplied --
    # google-auth mints a fresh access token from the refresh token the
    # first time it's actually needed (inside Request() below), the same
    # lazy-refresh behavior any OAuth2 client library gives you.
    return Credentials(
        token=None,
        refresh_token=refresh_token,
        token_uri="https://oauth2.googleapis.com/token",
        client_id=client_id,
        client_secret=client_secret,
        scopes=CALENDAR_SCOPES,
    )


# Talks to the Calendar REST API directly via `requests`, rather than
# through googleapiclient.discovery.build()'s default httplib2 transport --
# confirmed live on this dev machine that httplib2 cannot complete a TCP
# connection to googleapis.com at all (a bare `httplib2.Http(timeout=10)`
# GET times out every time), while `requests` (used just below for the
# OAuth token refresh, and by curl) reaches the exact same host in well
# under a second. httplib2 doesn't do IPv4/IPv6 Happy-Eyeballs fallback the
# way `requests`/urllib3 and curl do, so on a host with a broken/unreachable
# IPv6 route it can pick the dead address and hang -- `requests` avoiding
# that dependency entirely sidesteps the problem rather than working around
# it. Same two endpoints googleapiclient's calendar v3 service would have
# called (freeBusy.query, events.insert); response error handling collapses
# onto the same GoogleCalendarError callers already expect.
_REQUEST_TIMEOUT_SECONDS = 10


def _get_busy_blocks_sync(
    client_id: str, client_secret: str, refresh_token: str, calendar_id: str, start: date, end: date, timezone: str
) -> list[BusyBlock]:
    """The actual (synchronous, blocking) Google API call -- see this
    module's docstring for why GoogleCalendarProvider.get_busy_blocks below
    wraps this in asyncio.to_thread instead of calling it directly."""
    credentials = _build_credentials(client_id, client_secret, refresh_token)
    credentials.refresh(Request())

    # Google's freebusy API requires timeMin/timeMax to be full RFC3339
    # datetimes WITH a UTC offset -- a bare "2026-08-27T00:00:00" (no
    # offset) is invalid and Google rejects it with a plain, unhelpful
    # "400 Bad Request" (confirmed live, not just from the docs). The
    # "timeZone" field alone doesn't fix that -- it's the offset on
    # each timestamp itself Google actually validates. zoneinfo (Python
    # stdlib, no extra dependency) resolves the IANA zone name into a
    # real UTC offset for these two specific moments -- necessary, not
    # a fixed offset, because the same zone's offset can differ across
    # the range being queried (daylight saving time changes).
    tz = ZoneInfo(timezone)
    time_min = datetime.combine(start, time.min, tzinfo=tz)
    time_max = datetime.combine(end, time(23, 59, 59), tzinfo=tz)

    try:
        http_response = requests.post(
            "https://www.googleapis.com/calendar/v3/freeBusy",
            headers={"Authorization": f"Bearer {credentials.token}"},
            json={
                "timeMin": time_min.isoformat(),
                "timeMax": time_max.isoformat(),
                "timeZone": timezone,
                "items": [{"id": calendar_id}],
            },
            timeout=_REQUEST_TIMEOUT_SECONDS,
        )
        http_response.raise_for_status()
    except requests.RequestException as exc:
        raise GoogleCalendarError(f"Google Calendar freebusy query failed: {exc}") from exc

    # Response shape: {"calendars": {"<calendarId>": {"busy": [{"start": "...", "end": "..."}, ...]}}}
    calendar_result = http_response.json().get("calendars", {}).get(calendar_id, {})
    busy_periods = calendar_result.get("busy", [])
    return [BusyBlock(start=period["start"], end=period["end"]) for period in busy_periods]


def _create_event_sync(
    client_id: str,
    client_secret: str,
    refresh_token: str,
    calendar_id: str,
    summary: str,
    start: datetime,
    end: datetime,
    timezone: str,
    attendee_email: str,
    description: str,
) -> str:
    """The actual (synchronous, blocking) events.insert call -- see this
    module's docstring for why GoogleCalendarProvider.create_event below
    wraps this in asyncio.to_thread instead of calling it directly, same
    reasoning as _get_busy_blocks_sync above."""
    credentials = _build_credentials(client_id, client_secret, refresh_token)
    credentials.refresh(Request())

    try:
        http_response = requests.post(
            f"https://www.googleapis.com/calendar/v3/calendars/{calendar_id}/events",
            headers={"Authorization": f"Bearer {credentials.token}"},
            # sendUpdates=all is what makes Google email the invite (and
            # later reminders) to the attendee automatically -- this
            # agent's CLAUDE.md calls this out specifically ("reminders
            # sent automatically... no extra work") as the reason this
            # agent talks to Google Calendar directly rather than building
            # its own reminder system.
            params={"sendUpdates": "all"},
            json={
                "summary": summary,
                "description": description,
                "start": {"dateTime": start.isoformat(), "timeZone": timezone},
                "end": {"dateTime": end.isoformat(), "timeZone": timezone},
                "attendees": [{"email": attendee_email}],
            },
            timeout=_REQUEST_TIMEOUT_SECONDS,
        )
        http_response.raise_for_status()
    except requests.RequestException as exc:
        raise GoogleCalendarError(f"Google Calendar event creation failed: {exc}") from exc

    return http_response.json()["id"]


# credentials.refresh() (google-auth's own `requests` transport) has no
# timeout of its own -- confirmed live on this dev machine's flaky DNS, a
# token refresh alone once took 22s. _get_busy_blocks_sync/_create_event_sync
# now bound their own API call via requests' own `timeout=` (see
# _REQUEST_TIMEOUT_SECONDS above), but that leaves the refresh() step
# itself unbounded -- this outer bound catches that case too, so either
# step being slow still fails fast with a clear GoogleCalendarError (both
# callers already turn that into a proper 502 / "let me try that again"
# instead of a bare 500 or an indefinitely stuck voice turn) rather than
# hanging indefinitely.
_CALENDAR_CALL_TIMEOUT_SECONDS = 30


async def _bounded(func, *args):
    try:
        return await asyncio.wait_for(asyncio.to_thread(func, *args), timeout=_CALENDAR_CALL_TIMEOUT_SECONDS)
    except TimeoutError as exc:
        raise GoogleCalendarError(
            f"Google Calendar didn't respond within {_CALENDAR_CALL_TIMEOUT_SECONDS}s -- please try again."
        ) from exc


class GoogleCalendarProvider(CalendarProvider):
    """The one CalendarProvider implementation that exists today -- see
    calendar_provider.py's module docstring for why this class exists
    (abstraction, not Google-specific code spread through the app) and
    get_calendar_provider() for how a route obtains one.

    Constructed two ways (both via get_calendar_provider(), never directly
    by a route): with no arguments, for Mielikkix's own demo calendar
    (reads the global settings.google_calendar_* trio, obtained via
    scripts/connect_google_calendar.py's Desktop-app flow) -- or with an
    explicit client_id/secret/refresh_token/calendar_id, for a real
    business's own connected calendar (obtained via the Web-application
    OAuth flow in api/calendar_oauth.py, credentials read from that
    business's CalendarConnection row, refresh token decrypted immediately
    before use). The client_id/secret differ between these two cases
    because they're two different Google Cloud OAuth clients (Desktop app
    vs. Web application) -- a refresh token can only be refreshed with the
    client_id/secret of whichever OAuth client actually issued it.
    """

    def __init__(
        self,
        client_id: str | None = None,
        client_secret: str | None = None,
        refresh_token: str | None = None,
        calendar_id: str | None = None,
    ):
        self.client_id = client_id or settings.google_calendar_client_id
        self.client_secret = client_secret or settings.google_calendar_client_secret
        self.refresh_token = refresh_token or settings.google_calendar_refresh_token
        self.calendar_id = calendar_id or settings.google_calendar_id

    async def get_busy_blocks(self, start: date, end: date, timezone: str = "UTC") -> list[BusyBlock]:
        return await _bounded(
            _get_busy_blocks_sync,
            self.client_id,
            self.client_secret,
            self.refresh_token,
            self.calendar_id,
            start,
            end,
            timezone,
        )

    async def create_event(
        self,
        summary: str,
        start: datetime,
        end: datetime,
        timezone: str,
        attendee_email: str,
        description: str = "",
    ) -> str:
        return await _bounded(
            _create_event_sync,
            self.client_id,
            self.client_secret,
            self.refresh_token,
            self.calendar_id,
            summary,
            start,
            end,
            timezone,
            attendee_email,
            description,
        )
