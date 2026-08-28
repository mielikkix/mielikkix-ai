"""
Booking Assistant -- Phases 1-3 (see apps/agents/booking-assistant/CLAUDE.md
for the full phased plan: Phase 0 sets up a Google Cloud OAuth client and
connects one real test calendar).

Phase 1: one route that lists a real Google Calendar's busy blocks for a
given date range -- proves this app can talk to that calendar at all.
Phase 2: an LLM parses a free-text request ("book me 30 minutes next
Tuesday afternoon") into a structured date range, then busy blocks are
subtracted from business hours to get real open slots. Phase 3: given one
of those slots, re-check availability (never trust Phase 2's snapshot --
someone else may have booked in the meantime) and create a real Google
Calendar event, with the customer as an attendee so Google emails them the
invite automatically. Phase 4 (agent-to-agent handoff): Voice Receptionist
(app/api/agents_voice.py) now calls the exact same core logic via
app/services/booking_service.py -- see that module's own docstring for why
the logic lives there instead of here.

WHY THIS FILE LIVES IN apps/api, NOT apps/agents/booking-assistant: same
reason as app/api/agents_voice.py -- apps/api is the "shared modular agent
process" apps/agents/CLAUDE.md describes; apps/agents/booking-assistant
stays a CLAUDE.md + scaffold, not a second running process.

WHY THIS FILE IS THIN: every route below just parses its Pydantic request
body, calls into booking_service.py's plain functions, and maps the result
onto the response model -- the actual parsing/availability/booking logic
lives there so Voice Receptionist can call it too, without going through
HTTP or FastAPI's request/response cycle at all.
"""

from datetime import date, datetime

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query, Request
from pydantic import BaseModel
from sqlalchemy.orm import Session

from ..core.config import settings
from ..core.database import get_db
from ..core.limiter import limiter
from ..integrations.google_calendar_client import GoogleCalendarError
from ..notifications import notify_new_booking
from ..services import booking_service
from ..services.booking_service import _calendar_provider, _llm_client  # noqa: F401 -- re-exported for /dev/busy and this file's own tests

router = APIRouter(prefix="/api/agents/booking", tags=["booking-assistant"])


def _require_debug() -> None:
    """Same pattern as agents_voice.py's _require_debug -- gates the one
    remaining raw debugging route below (/dev/busy). /request and /confirm
    used to be debug-gated too during Phase 1-3 development, but are now
    the real routes the live chat widget/demo page call, so they're public
    (rate-limited instead, see request_booking/confirm_booking)."""
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
        busy_blocks = await _calendar_provider.get_busy_blocks(start, end, timezone)
    except GoogleCalendarError as exc:
        # 502 (Bad Gateway), not 500: this app is fine, the upstream Google
        # Calendar API is the one that failed/misbehaved (or credentials
        # aren't configured yet) -- 502 says that distinction to whoever's
        # debugging, the same way you'd want a failed upstream fetch() in a
        # TS backend to surface as "upstream failed" rather than "our own
        # code crashed".
        raise HTTPException(status_code=502, detail=str(exc)) from exc

    return {"busy": [{"start": block.start, "end": block.end} for block in busy_blocks]}


class _SlotOut(BaseModel):
    start: str  # ISO 8601, tz-aware -- pass back verbatim to /dev/confirm
    end: str


class _RequestBookingBody(BaseModel):
    message: str
    # The visitor's own IANA timezone (e.g. from the browser's
    # Intl.DateTimeFormat().resolvedOptions().timeZone), not something we
    # ask the LLM to guess from free text -- people almost never state their
    # timezone in a booking request, so parsing it out of the message would
    # mean asking a clarifying question on nearly every request. The client
    # already knows this precisely; just send it.
    timezone: str = "UTC"
    # Which tenant this booking is for -- omitted (None) by /dev/busy-style
    # internal callers and the standalone Mielikkix demo page, which always
    # mean Mielikkix's own demo calendar (see booking_service.py's
    # _resolve_calendar_provider). The live chat widget (apps/dashboard's
    # ChatWindow/BookingFlow) always sends its own business_id, since a
    # real tenant's booking must resolve to THAT business's own connected
    # calendar, never Mielikkix's.
    business_id: str | None = None


class _RequestBookingResponse(BaseModel):
    status: str  # "needs_selection" | "no_availability" | "clarification_needed" | "not_configured"
    slots: list[_SlotOut] = []
    clarification_question: str | None = None
    meeting_type: str | None = None
    duration_minutes: int | None = None


@router.post("/request", response_model=_RequestBookingResponse)
@limiter.limit("10/minute")
async def request_booking(request: Request, body: _RequestBookingBody, db: Session = Depends(get_db)):
    """Phase 2: turns a free-text request into real open slots. Public
    (not DEBUG-gated) -- unlike Phase 1's /dev/busy, this is what the real
    live demo (chat widget + /demo/booking-assistant) calls, so it needs to
    work in production. Rate-limited for the same reason leads.py's
    create_lead is: each call is a real LLM call plus a real Google
    Calendar read, both with a cost, reachable by anyone once it's not
    hidden behind DEBUG.

    CORS note: this goes through PublicRouteCORSMiddleware (app/core/cors.py),
    same as agents_support.py's own chat/message route -- a real tenant's
    booking flow (body.business_id set) runs from THEIR OWN chat widget,
    embedded on their own third-party website, so it must accept any
    origin. Safe to open the same way those other public routes are: no
    cookies/credentials, business_id-scoped (never touches another
    business's calendar, see booking_service.py's _resolve_calendar_provider),
    and rate-limited. Only a business_id=None call (the standalone Mielikkix
    demo page, Mielikkix's own sites) ever touches the demo calendar.

    All the actual parsing/availability logic lives in
    booking_service.resolve_booking_request() -- this route just maps its
    plain result onto the HTTP response shape.
    """
    try:
        result = await booking_service.resolve_booking_request(db, body.message, body.timezone, body.business_id)
    except GoogleCalendarError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc

    return _RequestBookingResponse(
        status=result.status,
        slots=[_SlotOut(start=slot.start.isoformat(), end=slot.end.isoformat()) for slot in result.slots],
        clarification_question=result.clarification_question,
        meeting_type=result.meeting_type,
        duration_minutes=result.duration_minutes,
    )


class _ConfirmBookingBody(BaseModel):
    name: str
    email: str
    phone: str | None = None
    # Exactly one of the {start, end} pairs /request returned in `slots` --
    # this route re-validates it's still free rather than trusting that
    # (see confirm_booking()'s docstring), but it isn't re-derived from
    # scratch here.
    start: str
    end: str
    timezone: str = "UTC"
    meeting_type: str = "appointment"
    # Ties the resulting Booking row back to the chat session that
    # triggered it, if this came from the chat-widget handoff rather than
    # the standalone demo page -- see models/booking.py's session_id.
    session_id: str | None = None
    # Same tenant-scoping field as _RequestBookingBody.business_id -- must
    # be the same value the visitor's /request call used, or confirm_booking
    # below resolves a different (or no) calendar than the slot was actually
    # offered against.
    business_id: str | None = None


class _ConfirmBookingResponse(BaseModel):
    status: str  # "booked" | "conflict" | "not_configured"
    event_id: str | None = None


@router.post("/confirm", response_model=_ConfirmBookingResponse)
@limiter.limit("10/minute")
async def confirm_booking(
    request: Request,
    body: _ConfirmBookingBody,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
):
    """Phase 3: books the slot the visitor picked from /request's list --
    but re-checks freebusy first rather than trusting that response, which
    may be stale by the time the visitor actually clicks "Confirm" (someone
    else could have booked the same slot in the meantime, or the server
    could have restarted between the two calls). This is the same "never
    trust a snapshot at confirmation time" rule this agent's CLAUDE.md calls
    out explicitly for exactly this reason. Public (not DEBUG-gated) and
    rate-limited, same reasoning as request_booking above.

    On success: persists a Booking row and fires a background notification
    to the business (see notifications.notify_new_booking) -- Google's own
    calendar invite (create_event's sendUpdates="all") already tells the
    CUSTOMER; this is the separate "the business found out too" step,
    mirroring exactly how api/leads.py's create_lead notifies a business of
    a new lead via notify_new_lead after committing the Lead row.

    The actual booking logic (freebusy re-check, event creation, Booking
    row, resolving who to notify) lives in
    booking_service.confirm_booking_slot() -- this route parses the request
    body's ISO datetime strings (an HTTP-input-specific concern; Voice
    Receptionist's tool executor already has real datetime objects, no
    parsing needed) and fires the notification via FastAPI's BackgroundTasks
    (also HTTP-specific -- a Twilio webhook handler has no BackgroundTasks
    available, so it fires notifications a different way, see
    agents_voice.py).
    """
    try:
        start = datetime.fromisoformat(body.start)
        end = datetime.fromisoformat(body.end)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=f"Invalid start/end: {exc}") from exc

    try:
        result = await booking_service.confirm_booking_slot(
            db,
            body.business_id,
            start,
            end,
            body.timezone,
            body.name,
            body.email,
            body.phone,
            body.meeting_type,
            body.session_id,
        )
    except GoogleCalendarError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc

    if result.status == "booked" and result.notify_email:
        background_tasks.add_task(notify_new_booking, result.notify_email, result.booking)

    return _ConfirmBookingResponse(status=result.status, event_id=result.event_id)
