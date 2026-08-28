"""
CalendarProvider -- abstraction around calendar operations, so Booking
Assistant (app/api/agents_booking.py) isn't tightly coupled to Google
Calendar specifically. Same idiom app/rag/providers/ already uses for
swapping LLM providers (an LLMProvider ABC + a get_llm_provider() factory in
that package's __init__.py) -- applied here to calendars, per "Mielikkix AI
-- Claude Code Project Instructions.md" Section 5: "Use an abstraction/
interface around calendar operations so the Booking Service is not tightly
coupled to Google Calendar... Google Calendar should be one implementation
of this interface."

Python note for a reader new to Python's abc module: `ABC` + `@abstractmethod`
is Python's version of a TypeScript `interface` (or an abstract base class in
C#) -- GoogleCalendarProvider below must implement every abstractmethod here
or Python refuses to let you instantiate it at all, the same guarantee a TS
`implements CalendarProvider` gives you at compile time, just enforced at
class-definition time instead.

Only get_busy_blocks/create_event are real (abstract) methods -- every phase
built so far (1-3 of this agent's CLAUDE.md) only ever needed those two.
get_event/update_event/delete_event are concrete methods here that just
raise NotImplementedError, rather than guessed-at abstract signatures no
phase has actually needed yet -- a future cancel/reschedule feature (this
agent's CLAUDE.md, "commit at the end of each phase") fills these in against
a real need, in whichever concrete provider actually implements it then.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import date, datetime


@dataclass
class BusyBlock:
    # Both ISO 8601 datetime strings, exactly as the provider's own API
    # returns them -- kept as raw strings rather than parsed into Python
    # datetimes since nothing here needs date arithmetic on them directly;
    # parse at whichever call site actually needs to compare them (see
    # app/api/agents_booking.py's _subtract_busy). Lives here (not in
    # google_calendar_client.py) because it's a generic calendar concept
    # every CalendarProvider implementation returns, not a Google-specific
    # response shape.
    start: str
    end: str


class CalendarProvider(ABC):
    @abstractmethod
    async def get_busy_blocks(self, start: date, end: date, timezone: str = "UTC") -> list[BusyBlock]:
        """The busy blocks on this provider's connected calendar between
        start and end (inclusive), in the given IANA timezone."""

    @abstractmethod
    async def create_event(
        self,
        summary: str,
        start: datetime,
        end: datetime,
        timezone: str,
        attendee_email: str,
        description: str = "",
    ) -> str:
        """Creates a real calendar event and returns the new event's ID.
        Callers must have already re-confirmed the slot is still free
        immediately before calling this (see agents_booking.py's
        confirm_booking) -- this does not re-check availability itself."""

    async def get_event(self, event_id: str):
        raise NotImplementedError(
            "Not needed until a feature reads an existing booking back (e.g. showing booking "
            "details in the dashboard) -- no phase of this agent's CLAUDE.md has needed it yet."
        )

    async def update_event(self, event_id: str, **changes):
        raise NotImplementedError(
            "Not needed until a reschedule-booking feature exists (this agent's CLAUDE.md's "
            "phased plan puts booking creation itself, Phase 3, before reschedule)."
        )

    async def delete_event(self, event_id: str):
        raise NotImplementedError(
            "Not needed until a cancel-booking feature exists (same phased-plan reasoning as "
            "update_event above)."
        )


def get_calendar_provider() -> CalendarProvider:
    """Only one implementation exists today (Google) -- this factory is the
    seam a future provider (Outlook, per the instructions doc's Section 5
    diagram) plugs into without agents_booking.py's routes changing at all,
    the same role get_llm_provider() plays in rag/providers/__init__.py for
    swapping Groq/Gemini/Ollama.
    """
    from .google_calendar_client import GoogleCalendarProvider

    return GoogleCalendarProvider()
