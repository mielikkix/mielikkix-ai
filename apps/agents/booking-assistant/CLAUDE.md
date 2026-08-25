# CLAUDE.md — apps/agents/booking-assistant

Read `apps/agents/CLAUDE.md` first (shared conventions across the three
flagship agents) — this file covers only what's specific to this one.

## What this agent does

Self-serve scheduling: a visitor describes what they want in plain language
("book me a 30-minute call next Tuesday afternoon") via the Chat Widget, a
Voice Receptionist handoff, or a direct booking link, and this agent turns
that into a real calendar booking, then sends reminders. Flagship agent —
second of the 10 to build.

## Why Cal.com underneath

Scheduling (availability math, double-booking prevention, reminders,
timezone handling, calendar sync) is a solved problem not worth rebuilding.
[Cal.com](https://cal.com) is open source and self-hostable — full control,
no per-booking fee, and a battle-tested engine underneath. This agent is an
**AI layer in front of Cal.com**, not a replacement for it: Cal.com owns
availability/bookings/reminders; this agent owns the natural-language
interface and the connections to the other two agents. Cal.com is a
separate third-party app (its own container, its own Postgres — see
`apps/agents/CLAUDE.md`), not one of the 10 Force agents.

## Self-hosting Cal.com — quick notes

- Deploy via Cal.com's official Docker image on the VPS, its own subdomain
  (e.g. `scheduling.mielikkix.ai`).
- Cal.com runs its own Postgres — don't reuse `packages/db` for it.
- Create an API key in Cal.com's settings for this agent to authenticate
  with, and set up the event type(s) (e.g. "30-min consultation") in
  Cal.com's own admin UI — this agent reads/writes bookings against that
  event type, it doesn't define scheduling rules itself.

## Integrations needed

- **Calendar/scheduling engine**: self-hosted Cal.com, via its API v2
  (`httpx` client in this agent's own `integrations/` module).
- **LLM**: `packages/agent-core`'s client — parses free-text requests into a
  structured query (`duration_minutes`, `earliest_date`, `latest_date`,
  `timezone`, `meeting_type`).
- **Reminders**: Cal.com sends its own confirmation/reminder emails by
  default. Only fall back to `apps/api/app/notifications` (Resend) for a
  branded email Cal.com can't produce — don't build a second reminder
  system.
- **Voice Receptionist / Support Triage handoff**: must accept a booking
  request via a direct function call from either agent (same process — see
  `apps/agents/CLAUDE.md`), as well as requests from the widget/dashboard
  directly.

## Data this agent stores

- This agent's own log of booking conversations and resulting booking IDs
  (`packages/db`, tenant-scoped) — separate from whatever Cal.com stores in
  its own database.

## Booking service (for the other two agents to call)

Exposed as a plain importable function, not an HTTP endpoint:

```
booking_assistant.service.create_booking(
    name: str, email: str, phone: str | None, request_description: str,
) -> BookingResult  # status: "booked" | "needs_selection" | "no_availability"
                     # + booking details or alternative slots
```

## Flow

1. Request comes in — from a visitor typing into the chat widget, or from
   another agent calling `create_booking(...)` on the caller's/visitor's
   behalf.
2. The LLM parses the free-text request into a structured query.
3. Query Cal.com's API for available slots matching that query.
4. Present the options (widget: a small picker; agent handoff: return the
   list so the calling agent can read it out or offer it).
5. On confirmation, create the booking via the Cal.com API.
6. Log the conversation + resulting booking ID to `packages/db`.

## Dashboard module

New "Bookings" tab in `apps/dashboard`, gated by entitlement: calendar/list
view of upcoming bookings, manual booking creation, cancellation.

## Development phases

1. **Phase 0 — Cal.com up**: self-host Cal.com on the VPS, create an event
   type, book one meeting manually through its own UI to confirm it works
   end to end, generate an API key.
2. **Phase 1 — Skeleton + Cal.com client**: a `calcom/client.py` wrapper, a
   route that lists available slots for a given date range (no AI yet —
   hardcode a query to prove the plumbing works).
3. **Phase 2 — NL parsing**: add the agent-core-backed parser turning free
   text into the structured slot query.
4. **Phase 3 — Booking creation**: complete the create-booking flow and
   confirmation messaging.
5. **Phase 4 — Agent handoff**: build `create_booking(...)` for Voice
   Receptionist and Support Triage to call; test it with a fake caller.
6. **Phase 5 — Chat widget**: build the booking UI in the Chat Widget flow.
7. **Phase 6 — Deploy**: wire into the shared modular agent process behind
   Caddy at `api.mielikkix.ai/api/agents/booking/...`.
8. **Phase 7 — Tests**: NL-parsing edge cases (ambiguous dates, past dates,
   unsupported durations) and the Cal.com client against a mocked API.

## Definition of done for the 8-day sprint

- [ ] Availability lookup works against Cal.com
- [ ] Booking created end-to-end from the Chat Widget flow
- [ ] Booking created end-to-end from a Voice Receptionist handoff
- [ ] Booking created end-to-end from a Support Triage handoff
- [ ] Reminder sent ahead of the appointment
- [ ] NL parser asks a clarifying question rather than guessing on
      ambiguous/relative dates ("next Tuesday", "sometime this week")
- [ ] Double-booking impossible — availability re-checked at confirmation
      time, not just at search time
- [ ] Bookings visible in dashboard, gated correctly by entitlement
- [ ] Deployed on the VPS, smoke-tested in production
