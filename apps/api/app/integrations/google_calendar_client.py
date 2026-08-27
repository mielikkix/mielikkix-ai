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
from dataclasses import dataclass
from datetime import date

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

from ..core.config import settings

# The only scope this agent needs: read freebusy + create/manage events it
# creates -- NOT full calendar read/write (calendar.readonly would block
# booking; the broader "calendar" scope would let this agent read/change
# events it never created, more access than it needs). Must exactly match
# the scope requested when the refresh token was obtained (see
# scripts/connect_google_calendar.py) -- Google rejects an API call made
# with a token that was never granted this scope.
CALENDAR_SCOPE = "https://www.googleapis.com/auth/calendar.events"


@dataclass
class BusyBlock:
    # Both ISO 8601 datetime strings in UTC, exactly as Google's freebusy
    # API returns them -- kept as raw strings rather than parsed into
    # Python datetimes for the same reason calcom_client.py's AvailableSlot
    # did: nothing here needs date arithmetic on them yet (Phase 1 scope),
    # parse at whichever call site actually needs to compare them.
    start: str
    end: str


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
        scopes=[CALENDAR_SCOPE],
    )


def _get_busy_blocks_sync(start: date, end: date, timezone: str) -> list[BusyBlock]:
    """The actual (synchronous, blocking) Google API call -- see this
    module's docstring for why get_busy_blocks() below wraps this in
    asyncio.to_thread instead of calling it directly."""
    credentials = _build_credentials()
    credentials.refresh(Request())

    service = build("calendar", "v3", credentials=credentials)
    try:
        response = (
            service.freebusy()
            .query(
                body={
                    # Google's freebusy API wants full RFC3339 datetimes,
                    # not bare dates -- midnight at the start of each day,
                    # in the caller's timezone (the "timeZone" field below
                    # is what makes "midnight" mean the right moment).
                    "timeMin": f"{start.isoformat()}T00:00:00",
                    "timeMax": f"{end.isoformat()}T23:59:59",
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


async def get_busy_blocks(start: date, end: date, timezone: str = "UTC") -> list[BusyBlock]:
    """The busy blocks on settings.google_calendar_id between start and end
    (inclusive), in the given IANA timezone -- Phase 1 scope only: this
    returns what's BUSY, not what's available. Turning "busy blocks" into
    "open slots the business would actually offer" means subtracting these
    from BusinessSettings.business_hours, which is Phase 2+ work (this
    agent's CLAUDE.md) once an LLM-parsed request exists to check
    availability for -- Phase 1 just proves this app can really talk to a
    real Google Calendar.
    """
    return await asyncio.to_thread(_get_busy_blocks_sync, start, end, timezone)


# create_event(...) (events.insert) arrives in Phase 3 (booking creation) --
# not written yet, per this agent's CLAUDE.md phased plan: Phase 1 is
# get_busy_blocks only, proven end-to-end, before anything books a real
# event.
