# apps/agents/booking-assistant

Flagship Force agent (build order: Day 5). Self-serve scheduling: a customer
picks a service/time via the Chat Widget, a Voice Receptionist handoff, or a
direct booking link, and this agent finds availability, confirms the slot,
and sends reminders.

See [`CLAUDE.md`](./CLAUDE.md) in this directory for integrations needed,
data model, and test criteria — read that before touching this agent's code.

Core flow is built and live: NL-parsed availability search, double-booking-safe
confirmation against a real Google Calendar, chat-widget handoff, and voice-agent
handoff. See [`CLAUDE.md`](./CLAUDE.md)'s "Current state" section for exact status
and remaining phases (per-tenant OAuth, dashboard Bookings tab, VPS deploy).
