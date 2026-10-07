# apps/agents/booking-assistant

Flagship Force agent (build order: Day 5). Self-serve scheduling: a customer
picks a service/time via the Chat Widget, a Voice Receptionist handoff, or a
direct booking link, and this agent finds availability, confirms the slot,
and sends reminders.

See [`CLAUDE.md`](./CLAUDE.md) in this directory for integrations needed,
data model, and test criteria — read that before touching this agent's code.

Built and live: each business connects its own Google Calendar (OAuth) and sets
its opening hours; NL-parsed availability search (Claude Sonnet), double-booking-safe
confirmation, real calendar invites, and handoffs from the Chat Widget, Support
Triage and Voice Receptionist. Code lives in `apps/api` (`app/api/agents_booking.py`,
`app/services/booking_service.py`, `app/api/calendar_oauth.py`). See
[`CLAUDE.md`](./CLAUDE.md)'s "Current state" for the remaining gaps (cancel/reschedule,
a tenant-facing Bookings tab).
