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
invite automatically. No agent-to-agent handoff yet (Phase 4) or per-tenant
OAuth/dashboard UI yet (Phase 5) -- both later commits, per this agent's
CLAUDE.md ("commit at the end of each phase, so the maintainer can follow
along").

WHY THIS FILE LIVES IN apps/api, NOT apps/agents/booking-assistant: same
reason as app/api/agents_voice.py -- apps/api is the "shared modular agent
process" apps/agents/CLAUDE.md describes; apps/agents/booking-assistant
stays a CLAUDE.md + scaffold, not a second running process.
"""

import json
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query, Request
from pydantic import BaseModel
from sqlalchemy.orm import Session

from mielikkix_agent_core import LLMClient

from ..core.config import settings
from ..core.database import get_db
from ..core.limiter import limiter
from ..integrations.calendar_provider import BusyBlock, CalendarProvider, get_calendar_provider
from ..integrations.google_calendar_client import GoogleCalendarError
from ..models.booking import Booking
from ..models.business import Business, BusinessSettings
from ..notifications import notify_new_booking
from ..services import plan_service

router = APIRouter(prefix="/api/agents/booking", tags=["booking-assistant"])

_llm_client = LLMClient()
# Module-level instance, same convention as _llm_client above -- resolved
# once via the CalendarProvider factory (see calendar_provider.py) rather
# than importing Google-specific functions directly, so this file has no
# knowledge of which calendar provider is actually behind it. Tests
# monkeypatch this instance's methods, same way they already monkeypatch
# _llm_client.chat.
_calendar_provider = get_calendar_provider()

# Weekday index (date.weekday(): Monday=0 ... Sunday=6) -> the key it maps
# to in BusinessSettings.business_hours (see schemas/business.py's
# BusinessHours) -- a day absent from the dict, or explicitly null, means
# closed that day.
_WEEKDAY_KEYS = ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]


def _resolve_calendar_provider(db: Session, business_id: str | None) -> CalendarProvider | None:
    """No business_id (the standalone demo page, /dev/busy, admin view):
    always the module-level Mielikkix demo provider above, unchanged from
    Phase 1-3.

    A real business_id (the live chat widget, once a tenant has gone
    through Booking Assistant's OAuth setup -- see api/calendar_oauth.py):
    resolves via the tenant-aware factory instead. Returns None if that
    business doesn't exist, isn't entitled (plan_service.require_feature,
    "booking_enabled"), or has no CalendarConnection yet -- callers turn
    that into a "not_configured" response rather than ever falling back to
    _calendar_provider, which would silently book onto Mielikkix's OWN
    calendar on that business's behalf (exactly the cross-tenant mistake
    this whole per-tenant design exists to prevent).
    """
    if business_id is None:
        return _calendar_provider

    business = db.query(Business).filter(Business.id == business_id).first()
    if business is None:
        return None
    try:
        plan_service.require_feature(business, "booking_enabled")
    except HTTPException:
        return None

    return get_calendar_provider(db, business_id)


def _resolve_business_hours(db: Session, business_id: str | None) -> dict | None:
    """The real per-tenant, per-weekday hours for a business_id-scoped
    /request call -- None (business_id is None, OR the business hasn't set
    any hours yet) tells _business_hours_window to fall back to the global
    settings.booking_agent_hours_start/_end Mon-Fri window, which is only
    ever correct for Mielikkix's own demo calendar, never a real tenant's.
    request_booking() below treats "None AND business_id was given" as
    not_configured, same reasoning as an unconnected calendar."""
    if business_id is None:
        return None
    biz_settings = db.query(BusinessSettings).filter(BusinessSettings.business_id == business_id).first()
    return biz_settings.business_hours if biz_settings else None


# How many open slots to hand back at once -- an unbounded list would be
# both a huge LLM-adjacent response and a bad picker UI. 8 is plenty for a
# few days of a typical Mon-Fri 9-5 window at a 30-60 minute duration.
_MAX_SLOTS_RETURNED = 8


# Python note for a reader new to Python coming from TS/Angular: a
# pydantic BaseModel here plays the same role a TS `interface` plus a
# runtime validator (e.g. zod) would together -- FastAPI/pydantic parse the
# LLM's raw JSON text straight into this shape and raise if a field is
# missing or the wrong type, instead of trusting the LLM's JSON blindly.
class _ParsedRequest(BaseModel):
    duration_minutes: int
    earliest_date: str  # "YYYY-MM-DD"; parsed to a real `date` by the caller
    latest_date: str
    meeting_type: str
    clarification_needed: bool
    clarification_question: str = ""


class _ParseError(Exception):
    """Raised when the LLM's response doesn't parse into _ParsedRequest, or
    the dates inside it don't make sense (unparsable, or latest before
    earliest, or entirely in the past) -- caught by dev_request_booking()
    so a bad LLM response degrades to a clarifying question instead of a
    500."""


_PARSE_SYSTEM_PROMPT_TEMPLATE = (
    "You are Booking Assistant, a scheduling assistant for a small "
    "business. A visitor has described what they want to book in plain "
    "language. Turn it into a structured JSON query for checking calendar "
    "availability.\n\n"
    "Today's date is {today} ({weekday}). Resolve any relative date "
    "(\"next Tuesday\", \"tomorrow\", \"this week\") against that.\n\n"
    'Respond with ONLY a JSON object (no other text), in exactly this '
    'shape:\n'
    '{{"duration_minutes": <integer, your best guess if not stated -- 30 '
    'for a typical short appointment>, '
    '"earliest_date": "<YYYY-MM-DD, the first day to check>", '
    '"latest_date": "<YYYY-MM-DD, the last day to check -- same as '
    'earliest_date if only one day was implied, otherwise a real range '
    'like a week out>", '
    '"meeting_type": "<a short label for what they want, e.g. '
    '\'consultation\', \'haircut\', \'call\'>", '
    '"clarification_needed": <true only if there is truly no way to infer '
    'even a reasonable date range -- e.g. \'I want to book something\' '
    'with no timeframe at all -- false otherwise, including for '
    'resolvable relative dates like \'next Tuesday\'>, '
    '"clarification_question": "<a short question to ask back, ONLY if '
    'clarification_needed is true, otherwise empty string -- ALWAYS end it '
    "with a quick example of an acceptable answer in parentheses, e.g. "
    "'Which date would you like to come in? (e.g. tomorrow afternoon, or "
    "next Tuesday)', so the visitor knows exactly what kind of reply to "
    'type back rather than guessing the format>"}}'
)

# LLM output is untrusted input from this app's own perspective (same as
# any other model completion) -- clamp to a sane range rather than trusting
# whatever number it returns, so a hallucinated "duration_minutes": 50000
# can't produce a nonsensical slot list.
_MIN_DURATION_MINUTES = 15
_MAX_DURATION_MINUTES = 240

# How far ahead a request is allowed to search -- keeps a hallucinated or
# malicious latest_date (e.g. ten years out) from turning one request into
# thousands of days of freebusy queries against the real Google Calendar.
_MAX_SEARCH_WINDOW_DAYS = 30


async def _parse_request(message: str) -> _ParsedRequest:
    today = date.today()
    system_prompt = _PARSE_SYSTEM_PROMPT_TEMPLATE.format(
        today=today.isoformat(), weekday=today.strftime("%A")
    )
    try:
        result = await _llm_client.chat(
            [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": message},
            ],
            json_mode=True,
            # LLMClient's own default (512) is too tight for this call --
            # confirmed live (a real groq.BadRequestError: "max completion
            # tokens reached before generating a valid document"): the
            # configured model (settings.groq_model, an OSS reasoning
            # model) can spend a chunk of its completion budget on
            # internal reasoning before ever emitting the actual JSON, so
            # a short, plain-looking message can still hit the cap
            # mid-object. This tiny JSON shape itself needs nowhere near
            # this many tokens; the headroom is entirely for that
            # reasoning overhead.
            max_tokens=1536,
        )
    except Exception as exc:
        # Any LLM-call-level failure (a real live example: groq.BadRequestError
        # when the model's completion budget ran out before finishing valid
        # JSON) used to propagate straight past this function as a raw 500 --
        # only a malformed-but-received response was ever caught below. This
        # degrades exactly like a malformed response does: a clarifying
        # question instead of a broken request, same "never leave the visitor
        # stuck" convention this route's own docstring already claims for the
        # JSON-parsing case.
        raise _ParseError(f"LLM call failed while parsing booking request: {exc}") from exc

    try:
        return _ParsedRequest(**json.loads(result.text))
    except (json.JSONDecodeError, TypeError, ValueError) as exc:
        raise _ParseError(f"Could not parse booking request JSON: {result.text!r}") from exc


def _resolve_date_range(parsed: _ParsedRequest) -> tuple[date, date]:
    """Turns _ParsedRequest's string dates into real `date` objects, and
    rejects anything nonsensical (unparsable, backwards, entirely in the
    past, or absurdly far out) by raising _ParseError -- the route below
    turns that into a clarifying-question response instead of a 500."""
    try:
        earliest = date.fromisoformat(parsed.earliest_date)
        latest = date.fromisoformat(parsed.latest_date)
    except ValueError as exc:
        raise _ParseError(f"Unparsable date in LLM response: {exc}") from exc

    today = date.today()
    if earliest < today:
        earliest = today
    if latest < earliest:
        raise _ParseError("latest_date is before earliest_date")
    if (latest - earliest).days > _MAX_SEARCH_WINDOW_DAYS:
        latest = earliest + timedelta(days=_MAX_SEARCH_WINDOW_DAYS)

    return earliest, latest


def _business_hours_window(
    day: date, tz: ZoneInfo, business_hours: dict | None = None
) -> tuple[datetime, datetime] | None:
    """The open/closed window for one calendar day, or None if the
    business is closed that day.

    business_hours=None (the standalone demo page, /dev/busy, admin view,
    or a business_id-scoped call with hours already confirmed present by
    the caller -- see _resolve_business_hours): Phase-1-style hardcoded
    Mon-Fri settings.booking_agent_hours_start/_end, weekends always
    closed -- Mielikkix's own demo calendar only.

    A real business_hours dict (schemas/business.py's BusinessHours shape,
    e.g. {"monday": {"open": "09:00", "close": "17:00"}, ..., "sunday":
    null}): looks up that day's own hours instead, closed if the key is
    missing or null.
    """
    if business_hours is not None:
        day_hours = business_hours.get(_WEEKDAY_KEYS[day.weekday()])
        if not day_hours:
            return None
        start_hour, start_minute = (int(part) for part in day_hours["open"].split(":"))
        end_hour, end_minute = (int(part) for part in day_hours["close"].split(":"))
    else:
        if day.weekday() >= 5:  # Python note: Monday=0 ... Sunday=6, so 5/6 = Sat/Sun
            return None
        start_hour, start_minute = (int(part) for part in settings.booking_agent_hours_start.split(":"))
        end_hour, end_minute = (int(part) for part in settings.booking_agent_hours_end.split(":"))

    open_at = datetime(day.year, day.month, day.day, start_hour, start_minute, tzinfo=tz)
    close_at = datetime(day.year, day.month, day.day, end_hour, end_minute, tzinfo=tz)
    return open_at, close_at


def _subtract_busy(
    window: tuple[datetime, datetime], busy_blocks: list[BusyBlock]
) -> list[tuple[datetime, datetime]]:
    """One day's open window, minus whatever part of it overlaps a busy
    block -- the actual "busy blocks -> available slots" arithmetic this
    agent's CLAUDE.md describes Google's API itself not doing for you.
    Returns the free sub-ranges left over, in order; a window with no
    overlapping busy blocks at all comes back as a single one-item list
    (itself, unchanged).
    """
    free_ranges = [window]
    for block in busy_blocks:
        busy_start = datetime.fromisoformat(block.start)
        busy_end = datetime.fromisoformat(block.end)
        next_ranges: list[tuple[datetime, datetime]] = []
        for range_start, range_end in free_ranges:
            # No overlap at all -- this free range is untouched by this
            # particular busy block.
            if busy_end <= range_start or busy_start >= range_end:
                next_ranges.append((range_start, range_end))
                continue
            # Overlaps -- keep whatever sliver comes before the busy block
            # started, and whatever sliver comes after it ended, dropping
            # the busy part itself. Either sliver might be empty (busy
            # block covers one whole end of the range); the length check
            # below drops those.
            if range_start < busy_start:
                next_ranges.append((range_start, busy_start))
            if busy_end < range_end:
                next_ranges.append((busy_end, range_end))
        free_ranges = next_ranges
    return free_ranges


def _slots_within(
    free_ranges: list[tuple[datetime, datetime]], duration: timedelta
) -> list[tuple[datetime, datetime]]:
    """Slices free time ranges into back-to-back `duration`-long slots,
    dropping any leftover shorter than a full slot at the end of a range."""
    slots = []
    for range_start, range_end in free_ranges:
        slot_start = range_start
        while slot_start + duration <= range_end:
            slots.append((slot_start, slot_start + duration))
            slot_start += duration
    return slots


def _available_slots_for_range(
    busy_blocks: list[BusyBlock],
    earliest: date,
    latest: date,
    duration_minutes: int,
    tz_name: str,
    business_hours: dict | None = None,
) -> list[tuple[datetime, datetime]]:
    """Phase 2's core: business hours minus busy blocks, sliced into
    duration_minutes slots, across every day from earliest to latest
    (inclusive). Pure function of its inputs (no I/O) so it's cheap to unit
    test directly against hand-built busy_blocks, same convention as
    keeping _classify()'s JSON handling separate from the HTTP layer in
    agents_support.py.
    """
    tz = ZoneInfo(tz_name)
    duration = timedelta(minutes=duration_minutes)
    slots: list[tuple[datetime, datetime]] = []

    day = earliest
    while day <= latest:
        window = _business_hours_window(day, tz, business_hours)
        if window is not None:
            free_ranges = _subtract_busy(window, busy_blocks)
            slots.extend(_slots_within(free_ranges, duration))
        day += timedelta(days=1)

    return slots[:_MAX_SLOTS_RETURNED]


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
    # mean Mielikkix's own demo calendar (see _resolve_calendar_provider).
    # The live chat widget (apps/dashboard's ChatWindow/BookingFlow) always
    # sends its own business_id, since a real tenant's booking must resolve
    # to THAT business's own connected calendar, never Mielikkix's.
    business_id: str | None = None


class _RequestBookingResponse(BaseModel):
    status: str  # "needs_selection" | "no_availability" | "clarification_needed" | "not_configured"
    slots: list[_SlotOut] = []
    clarification_question: str | None = None
    meeting_type: str | None = None
    duration_minutes: int | None = None


_GENERIC_CLARIFICATION = (
    "Sorry, I didn't quite catch when you'd like to come in. Could you say "
    "roughly what day (or day range) works, and what you'd like to book?"
)


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
    business's calendar, see _resolve_calendar_provider), and rate-limited.
    Only a business_id=None call (the standalone Mielikkix demo page,
    Mielikkix's own sites) ever touches the demo calendar.

    Two-step error handling worth noting for a reader new to Python's
    `try`/`except`: _ParseError covers both "the LLM's JSON didn't parse"
    AND "the dates inside it didn't make sense" (see
    _parse_request/_resolve_date_range) -- either one degrades to a
    clarifying question rather than a 500, same "never leave the visitor
    stuck" convention agents_support.py's chat_message() uses for its own
    LLM-failure fallback.
    """
    provider = _resolve_calendar_provider(db, body.business_id)
    business_hours = _resolve_business_hours(db, body.business_id)
    # A business_id was given, but there's no working Booking Assistant
    # setup for it yet (no connected calendar, no hours configured, plan
    # doesn't include it, or the business_id itself is bogus) -- checked
    # before spending an LLM call parsing body.message, since there'd be
    # nothing useful to do with the result either way.
    if provider is None or (body.business_id is not None and not business_hours):
        return _RequestBookingResponse(status="not_configured")

    try:
        parsed = await _parse_request(body.message)
    except _ParseError:
        return _RequestBookingResponse(
            status="clarification_needed", clarification_question=_GENERIC_CLARIFICATION
        )

    if parsed.clarification_needed:
        return _RequestBookingResponse(
            status="clarification_needed",
            clarification_question=parsed.clarification_question or _GENERIC_CLARIFICATION,
        )

    try:
        earliest, latest = _resolve_date_range(parsed)
    except _ParseError:
        return _RequestBookingResponse(
            status="clarification_needed", clarification_question=_GENERIC_CLARIFICATION
        )

    duration_minutes = max(_MIN_DURATION_MINUTES, min(_MAX_DURATION_MINUTES, parsed.duration_minutes))

    try:
        busy_blocks = await provider.get_busy_blocks(earliest, latest, body.timezone)
    except GoogleCalendarError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc

    slots = _available_slots_for_range(
        busy_blocks, earliest, latest, duration_minutes, body.timezone, business_hours
    )

    if not slots:
        return _RequestBookingResponse(
            status="no_availability", meeting_type=parsed.meeting_type, duration_minutes=duration_minutes
        )

    return _RequestBookingResponse(
        status="needs_selection",
        slots=[_SlotOut(start=s.isoformat(), end=e.isoformat()) for s, e in slots],
        meeting_type=parsed.meeting_type,
        duration_minutes=duration_minutes,
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
    """
    provider = _resolve_calendar_provider(db, body.business_id)
    if provider is None:
        return _ConfirmBookingResponse(status="not_configured")

    try:
        start = datetime.fromisoformat(body.start)
        end = datetime.fromisoformat(body.end)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=f"Invalid start/end: {exc}") from exc

    # A previously-offered slot that's already in the past by the time the
    # visitor confirms isn't a double-booking exactly, but it's just as
    # unbookable -- same "conflict" bucket rather than a third status the
    # UI would also have to handle.
    now = datetime.now(start.tzinfo)
    if start < now:
        return _ConfirmBookingResponse(status="conflict")

    try:
        busy_blocks = await provider.get_busy_blocks(start.date(), end.date(), body.timezone)
    except GoogleCalendarError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc

    for block in busy_blocks:
        busy_start = datetime.fromisoformat(block.start)
        busy_end = datetime.fromisoformat(block.end)
        if busy_start < end and start < busy_end:  # the two ranges overlap
            return _ConfirmBookingResponse(status="conflict")

    try:
        event_id = await provider.create_event(
            summary=f"{body.meeting_type} with {body.name}",
            start=start,
            end=end,
            timezone=body.timezone,
            attendee_email=body.email,
            description=f"Booked via Mielikkix Booking Assistant.\nPhone: {body.phone or 'not provided'}",
        )
    except GoogleCalendarError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc

    booking = Booking(
        session_id=body.session_id,
        name=body.name,
        email=body.email,
        phone=body.phone,
        meeting_type=body.meeting_type,
        start_at=start,
        end_at=end,
        calendar_event_id=event_id,
    )
    db.add(booking)
    db.commit()
    db.refresh(booking)

    # A business_id-scoped booking notifies THAT business's own contact
    # email, never Mielikkix's own settings.booking_notification_email --
    # otherwise every real tenant's booking would silently tell Mielikkix
    # about it instead of the tenant, the same cross-tenant mistake this
    # whole per-tenant design exists to prevent, just for notifications
    # instead of the calendar itself. No contact_email on file means no
    # notification goes out (never falls back to Mielikkix's own address).
    if body.business_id is not None:
        biz_settings = db.query(BusinessSettings).filter(BusinessSettings.business_id == body.business_id).first()
        notify_email = biz_settings.contact_email if biz_settings else None
    else:
        notify_email = settings.booking_notification_email

    if notify_email:
        background_tasks.add_task(notify_new_booking, notify_email, booking)

    return _ConfirmBookingResponse(status="booked", event_id=event_id)
