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
from datetime import date, datetime, time
from zoneinfo import ZoneInfo

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

from ..core.config import settings
from .calendar_provider import BusyBlock, CalendarProvider

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


def _build_credentials() -> Credentials:
    if not (
        settings.google_calendar_client_id
        and settings.google_calendar_client_secret
        and settings.google_calendar_refresh_token
    ):
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
        refresh_token=settings.google_calendar_refresh_token,
        token_uri="https://oauth2.googleapis.com/token",
        client_id=settings.google_calendar_client_id,
        client_secret=settings.google_calendar_client_secret,
        scopes=CALENDAR_SCOPES,
    )


def _get_busy_blocks_sync(start: date, end: date, timezone: str) -> list[BusyBlock]:
    """The actual (synchronous, blocking) Google API call -- see this
    module's docstring for why GoogleCalendarProvider.get_busy_blocks below
    wraps this in asyncio.to_thread instead of calling it directly."""
    credentials = _build_credentials()
    credentials.refresh(Request())

    service = build("calendar", "v3", credentials=credentials)
    try:
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

        response = (
            service.freebusy()
            .query(
                body={
                    "timeMin": time_min.isoformat(),
                    "timeMax": time_max.isoformat(),
                    "timeZone": timezone,
                    "items": [{"id": settings.google_calendar_id}],
                }
            )
            .execute()
        )
    except HttpError as exc:
        raise GoogleCalendarError(f"Google Calendar freebusy query failed: {exc}") from exc

    # Response shape: {"calendars": {"<calendarId>": {"busy": [{"start": "...", "end": "..."}, ...]}}}
    calendar_result = response.get("calendars", {}).get(settings.google_calendar_id, {})
    busy_periods = calendar_result.get("busy", [])
    return [BusyBlock(start=period["start"], end=period["end"]) for period in busy_periods]


def _create_event_sync(
    summary: str, start: datetime, end: datetime, timezone: str, attendee_email: str, description: str
) -> str:
    """The actual (synchronous, blocking) events.insert call -- see this
    module's docstring for why GoogleCalendarProvider.create_event below
    wraps this in asyncio.to_thread instead of calling it directly, same
    reasoning as _get_busy_blocks_sync above."""
    credentials = _build_credentials()
    credentials.refresh(Request())

    service = build("calendar", "v3", credentials=credentials)
    try:
        # .execute() both makes the real API call AND returns the created
        # event resource (a dict) -- captured here as `created` so its "id"
        # field can be returned below, the same way any REST client
        # returns the response body of a POST that creates something.
        created = (
            service.events()
            .insert(
                calendarId=settings.google_calendar_id,
                # sendUpdates="all" is what makes Google email the invite
                # (and later reminders) to the attendee automatically --
                # this agent's CLAUDE.md calls this out specifically
                # ("reminders sent automatically... no extra work") as the
                # reason this agent talks to Google Calendar directly
                # rather than building its own reminder system.
                sendUpdates="all",
                body={
                    "summary": summary,
                    "description": description,
                    "start": {"dateTime": start.isoformat(), "timeZone": timezone},
                    "end": {"dateTime": end.isoformat(), "timeZone": timezone},
                    "attendees": [{"email": attendee_email}],
                },
            )
            .execute()
        )
    except HttpError as exc:
        raise GoogleCalendarError(f"Google Calendar event creation failed: {exc}") from exc

    return created["id"]


class GoogleCalendarProvider(CalendarProvider):
    """The one CalendarProvider implementation that exists today -- see
    calendar_provider.py's module docstring for why this class exists
    (abstraction, not Google-specific code spread through the app) and
    get_calendar_provider() for how a route obtains one. Both methods below
    just delegate to the module-level sync helpers above via
    asyncio.to_thread -- see this file's own module docstring for why that
    hand-off to a background thread is necessary (googleapiclient is a
    synchronous, blocking library).
    """

    async def get_busy_blocks(self, start: date, end: date, timezone: str = "UTC") -> list[BusyBlock]:
        return await asyncio.to_thread(_get_busy_blocks_sync, start, end, timezone)

    async def create_event(
        self,
        summary: str,
        start: datetime,
        end: datetime,
        timezone: str,
        attendee_email: str,
        description: str = "",
    ) -> str:
        return await asyncio.to_thread(
            _create_event_sync, summary, start, end, timezone, attendee_email, description
        )
