"""
Booking Assistant -- Phase 1 (see apps/agents/booking-assistant/CLAUDE.md
for the full phased plan: Phase 0 sets up a Google Cloud OAuth client and
connects one real test calendar; this phase adds just enough plumbing to
prove this app can actually talk to that calendar).

Phase 1 scope, deliberately narrow: one route that lists a real Google
Calendar's busy blocks for a given date range. No natural-language parsing
yet (Phase 2), no business-hours subtraction turning "busy" into "available"
yet (also Phase 2), no booking creation yet (Phase 3), no agent-to-agent
handoff yet (Phase 4) -- each of those is a later commit, per this agent's
CLAUDE.md ("commit at the end of each phase, so the maintainer can follow
along").

WHY THIS FILE LIVES IN apps/api, NOT apps/agents/booking-assistant: same
reason as app/api/agents_voice.py -- apps/api is the "shared modular agent
process" apps/agents/CLAUDE.md describes; apps/agents/booking-assistant
stays a CLAUDE.md + scaffold, not a second running process.
"""

from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query

from ..core.config import settings
from ..integrations.google_calendar_client import GoogleCalendarError, get_busy_blocks

router = APIRouter(prefix="/api/agents/booking", tags=["booking-assistant"])


def _require_debug() -> None:
    """Same pattern as agents_voice.py's _require_debug: this route talks to
    a real Google Calendar and (once Phase 3 adds booking creation) will be
    able to create real events on it, so it stays behind DEBUG until a
    phase actually needs it public -- 404, not 403, so it gives no hint to
    an outsider that the route exists at all while it's off."""
    if not settings.debug:
        raise HTTPException(status_code=404, detail="Not found")


@router.get("/dev/busy", dependencies=[Depends(_require_debug)])
async def dev_list_busy_blocks(
    # Query(...) with no default means these are REQUIRED query params --
    # Python note: this is FastAPI's equivalent of an Angular route's
    # required @Input()/query param validation, done declaratively via the
    # function signature's type hints instead of an imperative check you'd
    # write yourself.
    start: date = Query(..., description="First date to check, YYYY-MM-DD"),
    end: date = Query(..., description="Last date to check (inclusive), YYYY-MM-DD"),
    timezone: str = Query("UTC", description="IANA timezone name, e.g. America/New_York"),
):
    """Proves the Google Calendar plumbing works end-to-end: real OAuth
    token refresh, real API call, real response -- against
    settings.google_calendar_id. This deliberately returns busy blocks, not
    "available slots": turning that into what a business would actually
    offer means subtracting these from BusinessSettings.business_hours,
    which is Phase 2's job (once an LLM parses a caller's free-text request
    into this same start/end/timezone shape). This route just takes them
    directly as query params so the plumbing can be proven without either
    layer existing yet.
    """
    try:
        busy_blocks = await get_busy_blocks(start, end, timezone)
    except GoogleCalendarError as exc:
        # 502 (Bad Gateway), not 500: this app is fine, the upstream Google
        # Calendar API is the one that failed/misbehaved (or credentials
        # aren't configured yet) -- 502 says that distinction to whoever's
        # debugging, the same way you'd want a failed upstream fetch() in a
        # TS backend to surface as "upstream failed" rather than "our own
        # code crashed".
        raise HTTPException(status_code=502, detail=str(exc)) from exc

    return {"busy": [{"start": block.start, "end": block.end} for block in busy_blocks]}
