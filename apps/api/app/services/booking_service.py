"""Booking Assistant's core logic, extracted out of app/api/agents_booking.py
so it's callable from a non-HTTP context too -- specifically, Voice
Receptionist's tool-calling loop (app/api/agents_voice.py), which needs the
exact same "parse a request -> find real slots -> book one" logic but has no
FastAPI request/response cycle, no rate limiter, and needs plain results
(never an HTTPException) since a phone call has no HTTP status code to hand
back.

This is the target shape apps/agents/booking-assistant/CLAUDE.md already
documents: a plain importable service, called in-process by whichever agent
needs it (apps/agents/CLAUDE.md's "shared modular agent process" convention),
rather than one agent making an HTTP request to another's own routes.

agents_booking.py's HTTP routes are now thin wrappers: parse the Pydantic
request body, call resolve_booking_request()/confirm_booking_slot() here,
map the plain result onto the existing response models (unchanged wire
shape, so the chat widget/dashboard/demo page see zero difference). Voice's
tool executor calls the exact same two functions and maps the result onto
what the LLM should say instead.
"""

import json
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

from sqlalchemy.orm import Session

from mielikkix_agent_core import LLMClient
from pydantic import BaseModel

from ..core.config import settings
from ..integrations.calendar_provider import BusyBlock, CalendarProvider, get_calendar_provider
from ..models.booking import Booking
from ..models.business import Business, BusinessSettings
from ..services import plan_service
from fastapi import HTTPException

# Booking Agent's model tier: Anthropic (settings.anthropic_model, default
# claude-sonnet-5) -- this is the SHARED "parse a free-text request into a
# structured date range" call every entry point funnels through (Voice
# Receptionist's tool executor AND the standalone Booking Assistant chat
# widget/demo page both call resolve_booking_request(), which calls
# _parse_request(), which uses this client -- see this module's own
# docstring). Deliberately the higher-reasoning tier: getting a caller's
# vague "sometime next week, afternoons work best" into a correct date
# range and duration is exactly the "strong multi-turn reasoning,
# structured tool use" case Claude Sonnet is assigned to, not the
# lower-stakes cheap tier.
_llm_client = LLMClient(provider="anthropic")
# Module-level instance, resolved once via the CalendarProvider factory (see
# calendar_provider.py) rather than importing Google-specific functions
# directly, so this module has no knowledge of which calendar provider is
# actually behind it. Tests monkeypatch this instance's methods directly
# (mutating the shared object, not rebinding this name), which keeps working
# unchanged from wherever it's imported -- agents_booking.py re-imports this
# same object for its own /dev/busy route and its own tests.
_calendar_provider = get_calendar_provider()

# Weekday index (date.weekday(): Monday=0 ... Sunday=6) -> the key it maps
# to in BusinessSettings.business_hours (see schemas/business.py's
# BusinessHours) -- a day absent from the dict, or explicitly null, means
# closed that day.
_WEEKDAY_KEYS = ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]


def _resolve_calendar_provider(db: Session, business_id: str | None) -> CalendarProvider | None:
    """No business_id (the standalone demo page, /dev/busy, admin view, and
    every voice call today -- see agents_voice.py's own module docstring on
    why): always the module-level Mielikkix demo provider above, unchanged
    from Phase 1-3.

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
    request -- None (business_id is None, OR the business hasn't set any
    hours yet) tells _business_hours_window to fall back to the global
    settings.booking_agent_hours_start/_end Mon-Fri window, which is only
    ever correct for Mielikkix's own demo calendar, never a real tenant's.
    resolve_booking_request() below treats "None AND business_id was given"
    as not_configured, same reasoning as an unconnected calendar."""
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
    earliest, or entirely in the past) -- caught by resolve_booking_request()
    so a bad LLM response degrades to a clarifying question instead of a
    crash."""


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

# The fallback question used whenever a request can't be parsed at all (the
# LLM call itself failed, its JSON didn't parse, or the dates inside it
# didn't make sense) -- a single source of truth so the chat widget and
# voice get the exact same wording for the exact same failure.
GENERIC_CLARIFICATION = (
    "Sorry, I didn't quite catch when you'd like to come in. Could you say "
    "roughly what day (or day range) works, and what you'd like to book?"
)


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
        # stuck" convention this module's callers already rely on.
        raise _ParseError(f"LLM call failed while parsing booking request: {exc}") from exc

    try:
        return _ParsedRequest(**json.loads(result.text))
    except (json.JSONDecodeError, TypeError, ValueError) as exc:
        raise _ParseError(f"Could not parse booking request JSON: {result.text!r}") from exc


def _resolve_date_range(parsed: _ParsedRequest) -> tuple[date, date]:
    """Turns _ParsedRequest's string dates into real `date` objects, and
    rejects anything nonsensical (unparsable, backwards, entirely in the
    past, or absurdly far out) by raising _ParseError -- the caller turns
    that into a clarifying-question response instead of a crash."""
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
    every voice call today, or a business_id-scoped call with hours already
    confirmed present by the caller -- see _resolve_business_hours):
    Phase-1-style hardcoded Mon-Fri settings.booking_agent_hours_start/_end,
    weekends always closed -- Mielikkix's own demo calendar only.

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
    block -- the actual "busy blocks -> available slots" arithmetic Google's
    API itself doesn't do for you. Returns the free sub-ranges left over, in
    order; a window with no overlapping busy blocks at all comes back as a
    single one-item list (itself, unchanged).
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
    """Business hours minus busy blocks, sliced into duration_minutes slots,
    across every day from earliest to latest (inclusive). Pure function of
    its inputs (no I/O) so it's cheap to unit test directly against
    hand-built busy_blocks.
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


@dataclass
class SlotOption:
    start: datetime
    end: datetime


@dataclass
class ResolveBookingResult:
    status: str  # "needs_selection" | "no_availability" | "clarification_needed" | "not_configured"
    slots: list[SlotOption] = field(default_factory=list)
    meeting_type: str | None = None
    duration_minutes: int | None = None
    clarification_question: str | None = None


async def resolve_booking_request(
    db: Session, message: str, timezone: str, business_id: str | None
) -> ResolveBookingResult:
    """Turns a free-text request into real open slots -- the shared core of
    what used to be agents_booking.py's request_booking() route body.
    Raises GoogleCalendarError uncaught (a plain, framework-agnostic
    exception) if the upstream Calendar API fails; each caller (an HTTP
    route, or Voice Receptionist's tool executor) decides its own fallback
    for that rather than this function assuming an HTTP response is even
    possible.
    """
    provider = _resolve_calendar_provider(db, business_id)
    business_hours = _resolve_business_hours(db, business_id)
    # A business_id was given, but there's no working Booking Assistant
    # setup for it yet (no connected calendar, no hours configured, plan
    # doesn't include it, or the business_id itself is bogus) -- checked
    # before spending an LLM call parsing the message, since there'd be
    # nothing useful to do with the result either way.
    if provider is None or (business_id is not None and not business_hours):
        return ResolveBookingResult(status="not_configured")

    try:
        parsed = await _parse_request(message)
    except _ParseError:
        return ResolveBookingResult(status="clarification_needed", clarification_question=GENERIC_CLARIFICATION)

    if parsed.clarification_needed:
        return ResolveBookingResult(
            status="clarification_needed",
            clarification_question=parsed.clarification_question or GENERIC_CLARIFICATION,
        )

    try:
        earliest, latest = _resolve_date_range(parsed)
    except _ParseError:
        return ResolveBookingResult(status="clarification_needed", clarification_question=GENERIC_CLARIFICATION)

    duration_minutes = max(_MIN_DURATION_MINUTES, min(_MAX_DURATION_MINUTES, parsed.duration_minutes))

    busy_blocks = await provider.get_busy_blocks(earliest, latest, timezone)

    slots = _available_slots_for_range(busy_blocks, earliest, latest, duration_minutes, timezone, business_hours)

    if not slots:
        return ResolveBookingResult(
            status="no_availability", meeting_type=parsed.meeting_type, duration_minutes=duration_minutes
        )

    return ResolveBookingResult(
        status="needs_selection",
        slots=[SlotOption(start=s, end=e) for s, e in slots],
        meeting_type=parsed.meeting_type,
        duration_minutes=duration_minutes,
    )


@dataclass
class ConfirmBookingResult:
    status: str  # "booked" | "conflict" | "not_configured"
    event_id: str | None = None
    booking: Booking | None = None
    # Resolved but NOT fired here -- how a caller notifies the business
    # differs by context (FastAPI's BackgroundTasks in an HTTP route vs.
    # asyncio.create_task in a Twilio webhook handler with no BackgroundTasks
    # available), so firing it is each caller's own job.
    notify_email: str | None = None


async def confirm_booking_slot(
    db: Session,
    business_id: str | None,
    start: datetime,
    end: datetime,
    timezone: str,
    name: str,
    email: str,
    phone: str | None,
    meeting_type: str,
    session_id: str | None,
) -> ConfirmBookingResult:
    """Books the given slot -- but re-checks freebusy first rather than
    trusting the caller's snapshot, which may be stale by the time this
    actually runs (someone else could have booked the same slot in the
    meantime). This is the shared core of what used to be
    agents_booking.py's confirm_booking() route body. Raises
    GoogleCalendarError uncaught, same reasoning as resolve_booking_request
    above.
    """
    provider = _resolve_calendar_provider(db, business_id)
    if provider is None:
        return ConfirmBookingResult(status="not_configured")

    # A previously-offered slot that's already in the past by the time this
    # runs isn't a double-booking exactly, but it's just as unbookable --
    # same "conflict" bucket rather than a third status every caller would
    # also have to handle.
    now = datetime.now(start.tzinfo)
    if start < now:
        return ConfirmBookingResult(status="conflict")

    busy_blocks = await provider.get_busy_blocks(start.date(), end.date(), timezone)

    for block in busy_blocks:
        busy_start = datetime.fromisoformat(block.start)
        busy_end = datetime.fromisoformat(block.end)
        if busy_start < end and start < busy_end:  # the two ranges overlap
            return ConfirmBookingResult(status="conflict")

    event_id = await provider.create_event(
        summary=f"{meeting_type} with {name}",
        start=start,
        end=end,
        timezone=timezone,
        attendee_email=email,
        description=f"Booked via Mielikkix Booking Assistant.\nPhone: {phone or 'not provided'}",
    )

    booking = Booking(
        session_id=session_id,
        name=name,
        email=email,
        phone=phone,
        meeting_type=meeting_type,
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
    if business_id is not None:
        biz_settings = db.query(BusinessSettings).filter(BusinessSettings.business_id == business_id).first()
        notify_email = biz_settings.contact_email if biz_settings else None
    else:
        notify_email = settings.booking_notification_email

    return ConfirmBookingResult(status="booked", event_id=event_id, booking=booking, notify_email=notify_email)
