# CLAUDE.md — apps/agents/booking-assistant

Read `apps/agents/CLAUDE.md` first (shared conventions across the three
flagship agents) — this file covers only what's specific to this one.

## What this agent does

Self-serve scheduling: a visitor describes what they want in plain language
("book me a 30-minute call next Tuesday afternoon") via the Chat Widget, a
Voice Receptionist handoff, or a direct booking link, and this agent turns
that into a real calendar booking, then sends reminders. Flagship agent —
second of the 10 to build.

## Why Google Calendar directly (not Cal.com)

Originally planned as an AI layer in front of self-hosted Cal.com. Reversed
after actually trying it: Cal.com (recently rebranded upstream to
"cal.diy") is now a large Next.js monorepo + a separate NestJS API service
+ Redis + its own Postgres — self-hosting it for local dev OOM-crashed
Docker Desktop twice on a from-source build, and it's a heavy, multi-
service footprint to run permanently on the VPS just for scheduling.

Google Calendar directly is a better fit for this product's actual
customers: small businesses that already live in Google Calendar day to
day. **Bookings land on the business owner's own calendar** — no separate
scheduling engine for them to look at, no separate thing for us to
self-host or pay to run. This agent owns availability math, double-booking
prevention, and booking creation itself (Google Calendar's API is just
calendar data — `freebusy.query` and `events.insert` — not a scheduling
engine), grounded in `BusinessSettings.business_hours` (already exists,
`apps/api/app/models/business.py`) for what counts as available.

## Connecting a business's calendar — OAuth, per tenant

Each business connects **their own** Google account once, via a "Connect
Google Calendar" button in `apps/dashboard` — NOT one shared calendar for
every tenant. This is a real OAuth 2.0 Authorization Code flow (not a
static API key like Cal.com used):

1. Business owner clicks connect → redirected to Google's consent screen
   (scope: `https://www.googleapis.com/auth/calendar.events`, the
   least-privilege scope that can read freebusy + create events without
   full calendar read/write access).
2. Google redirects back to our callback route with an auth code.
3. Exchange the code for an access token + **refresh token** — the refresh
   token is what's actually stored (long-lived; access tokens expire in
   ~1 hour and are re-minted from it on demand). Encrypt at rest, same
   convention as any other tenant secret in `packages/db`.
4. Every future availability/booking call for that business uses its own
   stored refresh token — never a token belonging to a different tenant.

Requires a Google Cloud project with the Calendar API enabled and an OAuth
2.0 Client ID — created once via Google Cloud Console, a human setup step
(Phase 0), same role Cal.com's admin UI played before. Two different client
types serve two different purposes here, both from the same Google Cloud
project:

- **Phase 0/1 (local dev)**: a "Desktop app" Client ID —
  `scripts/connect_google_calendar.py` uses Google's installed-app OAuth
  flow (opens your browser, no fixed redirect URI to register) to connect
  one real test calendar.
- **Phase 5 (production, per real tenant)**: a separate "Web application"
  Client ID, with this app's real callback URL as an authorized redirect
  URI — the dashboard's actual "Connect Google Calendar" button redirects
  through this one instead.

## Integrations needed

- **Calendar**: Google Calendar API v3, via `google-api-python-client` +
  `google-auth-oauthlib` (official Google client libraries — do not hand-roll
  the OAuth token refresh dance) in this agent's own `integrations/` module.
- **LLM**: `packages/agent-core`'s client — parses free-text requests into a
  structured query (`duration_minutes`, `earliest_date`, `latest_date`,
  `timezone`, `meeting_type`).
- **Reminders**: Google Calendar auto-emails invites/reminders to attendees
  by default — satisfies "reminders sent automatically" with no extra work.
  Only fall back to `apps/api/app/notifications` (Resend) for a branded
  email Google's own invite can't produce — don't build a second reminder
  system.
- **Voice Receptionist / Support Triage handoff**: must accept a booking
  request via a direct function call from either agent (same process — see
  `apps/agents/CLAUDE.md`), as well as requests from the widget/dashboard
  directly.

## Data this agent stores

- Per-business Google OAuth refresh token + which calendar ID to book
  against (`packages/db`, tenant-scoped, encrypted at rest).
- This agent's own log of booking conversations and resulting Google
  Calendar event IDs (`packages/db`, tenant-scoped).

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
3. Query Google Calendar's `freebusy.query` for the business's connected
   calendar, then subtract busy blocks from `business_hours` ourselves to
   get real open slots — Google's API only tells you what's busy, this
   agent decides what "available" means for that business.
4. Present the options (widget: a small picker; agent handoff: return the
   list so the calling agent can read it out or offer it).
5. On confirmation, re-check freebusy (never trust step 3's result is still
   true — someone else may have booked in the meantime) and create the
   event via `events.insert`, with the customer as an attendee so Google
   emails them the invite/reminder automatically.
6. Log the conversation + resulting Google Calendar event ID to
   `packages/db`.

## Dashboard module

New "Bookings" tab in `apps/dashboard`, gated by entitlement: calendar/list
view of upcoming bookings, manual booking creation, cancellation.

## Development phases

1. **Phase 0 — Google Cloud OAuth client**: create a Google Cloud project,
   enable the Calendar API, create an OAuth 2.0 Client ID ("Web
   application") with this app's callback URL as an authorized redirect
   URI, connect one real test calendar through the OAuth flow to confirm it
   works end to end.
2. **Phase 1 — Skeleton + Google Calendar client**: a
   `google_calendar_client.py` wrapper, a route that lists real busy blocks
   for a given date range against one hardcoded connected calendar (no
   business-hours subtraction yet, no AI yet, no dashboard OAuth UI yet —
   hardcode a query to prove the plumbing works; turning "busy" into
   "available" against `business_hours` is Phase 2, once there's an
   LLM-parsed request to check availability for).
3. **Phase 2 — NL parsing**: add the agent-core-backed parser turning free
   text into the structured slot query.
4. **Phase 3 — Booking creation**: complete the create-booking flow and
   confirmation messaging.
5. **Phase 4 — Agent handoff**: build `create_booking(...)` for Voice
   Receptionist and Support Triage to call; test it with a fake caller.
6. **Phase 5 — Chat widget + dashboard OAuth UI**: build the booking UI in
   the Chat Widget flow, and the real "Connect Google Calendar" button in
   `apps/dashboard` (Phase 1 hardcoded one calendar; this replaces that with
   the real per-business OAuth flow).
7. **Phase 6 — Deploy**: wire into the shared modular agent process behind
   Caddy at `api.mielikkix.ai/api/agents/booking/...`.
8. **Phase 7 — Tests**: NL-parsing edge cases (ambiguous dates, past dates,
   unsupported durations) and the Google Calendar client against a mocked
   API (never a real Google account in tests).

## Definition of done for the 8-day sprint

- [ ] A business can connect their Google Calendar via OAuth from the
      dashboard
- [ ] Availability lookup works against a real connected calendar
- [ ] Booking created end-to-end from the Chat Widget flow
- [ ] Booking created end-to-end from a Voice Receptionist handoff
- [ ] Booking created end-to-end from a Support Triage handoff
- [ ] Reminder sent ahead of the appointment (Google's own invite email)
- [ ] NL parser asks a clarifying question rather than guessing on
      ambiguous/relative dates ("next Tuesday", "sometime this week")
- [ ] Double-booking impossible — availability re-checked at confirmation
      time, not just at search time
- [ ] Bookings visible in dashboard, gated correctly by entitlement
- [ ] Deployed on the VPS, smoke-tested in production
