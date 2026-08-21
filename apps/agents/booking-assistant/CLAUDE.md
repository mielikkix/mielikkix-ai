# CLAUDE.md — apps/agents/booking-assistant

Place this file at `mielikkix-ai/apps/agents/booking-assistant/CLAUDE.md`.

## What this agent does

Self-serve scheduling: a customer picks a service/time via the Chat Widget, Voice
Receptionist handoff, or a direct booking link, and this agent finds availability,
confirms the slot, and sends reminders. Flagship agent — second of the 10 to build.

## Integrations needed

- **Calendar**: either a connected calendar (Google Calendar / Outlook API) per tenant,
  or an internal availability model stored in `packages/db` if the tenant doesn't
  connect an external calendar. Decide per-tenant which mode applies before building
  the UI around it.
- **Reminders**: reuse the same notification channel as the rest of the platform
  (SMS/email) — do not build a separate reminder system.
- **Voice Receptionist handoff**: must accept a booking request handed off mid-call
  (see that agent's CLAUDE.md) as well as requests coming directly from the widget
  or dashboard.

## Data this agent stores

- Services/time slots per tenant.
- Bookings (customer info, time, service, status, source: widget/voice/direct).
- Reminder send log.

## Dashboard module

New "Bookings" tab in `apps/dashboard`, gated by entitlement: calendar/list view of
upcoming bookings, manual booking creation, cancellation.

## Definition of done for the 8-day sprint

- [ ] Availability lookup works against at least one calendar mode (external or internal)
- [ ] Booking created end-to-end from the Chat Widget flow
- [ ] Booking created end-to-end from a Voice Receptionist handoff
- [ ] Reminder sent ahead of the appointment
- [ ] Bookings visible in dashboard, gated correctly by entitlement
- [ ] Deployed on the VPS, smoke-tested in production
