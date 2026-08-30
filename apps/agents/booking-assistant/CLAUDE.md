# CLAUDE.md — apps/agents/booking-assistant

Read `apps/agents/CLAUDE.md` first (shared conventions across the three
flagship agents) — this file covers only what's specific to this one. Also
read `files/Mielikkix AI — Claude Code Project Instructions.md` (Sections
4-6, 14-16) — that's the authoritative target architecture (calendar-
provider abstraction, the live-demo goal, the Mielikkix-owned demo
account/calendar) this file's own phased plan below is being built toward.

## Current state (as of the chat-widget handoff work)

Phases 1-3 below are done and live, but against **Mielikkix's own demo
setup**, not real per-tenant OAuth yet (that's still Phase 5 — see "Current
gaps" at the end of this section):

- `app/api/agents_booking.py`: `POST /api/agents/booking/request` (Phase 2:
  free text → real open slots) and `POST /api/agents/booking/confirm`
  (Phase 3: re-check + real Google Calendar event) are public routes now,
  not DEBUG-gated dev routes — they're what the live chat widget and
  `/demo/booking-assistant` actually call. `GET /api/agents/booking/dev/busy`
  stays DEBUG-gated; it's a raw internal debugging tool only.
- `app/integrations/calendar_provider.py`: the `CalendarProvider`
  abstraction this file's "Why Google Calendar directly" section below
  calls for — `GoogleCalendarProvider` (in `google_calendar_client.py`) is
  the one implementation today, obtained via `get_calendar_provider()`.
  `agents_booking.py` depends on the interface, not Google-specific code
  directly.
- `app/models/booking.py`'s `Booking` (no `business_id` yet — see that
  file's own comment, same reasoning as `Ticket`'s) persists each
  confirmation, and `notifications.notify_new_booking` emails
  `settings.booking_notification_email` (`post@mielikkix.no` by default) —
  Google's own invite (`sendUpdates="all"`) already tells the customer;
  this is the separate "the business found out" step, mirroring
  `api/leads.py`'s lead-notification pattern.
- **Chat widget handoff** (doc Section 14's diagram): `rag/pipeline.py`'s
  `_detect_intent` now has a `"booking"` branch (checked before `"lead"`),
  and `chat_service.py` sets `suggest_booking_flow` on the chat response
  when it fires. `apps/dashboard/src/widget/BookingFlow.tsx` (mirrors
  `LeadForm.tsx`'s pattern) renders inline in `ChatWindow.tsx` when that
  flag is set, seeded with the visitor's own triggering message, and calls
  the two public routes above directly — the chatbot itself never calls
  Booking Assistant's tools (doc Section 3: "chatbot should NOT contain
  hardcoded booking logic").
- **Demo account — DONE.** Switched from a personal Gmail (used during
  initial Phase 1-3 development) to the dedicated `mielikkix@gmail.com`
  account (doc Sections 5, 15) by re-running
  `scripts/connect_google_calendar.py` signed in as that account and
  updating `.env`'s `GOOGLE_CALENDAR_REFRESH_TOKEN`. Verified end-to-end: a
  real booking lands on `mielikkix@gmail.com`'s calendar (not the old
  personal one), the customer gets a real Google Calendar invite, and
  `post@mielikkix.no` gets the real booking-notification email via Resend.
  `GOOGLE_CALENDAR_ID` is still `"primary"` — a secondary "Mielikkix Demo
  Bookings" calendar on that account (doc Section 5's suggestion, to keep
  demo bookings out of the account's main calendar view) hasn't been
  created yet; that's a quick follow-up whenever it matters, not a
  functional gap.
  Note: the Google Cloud OAuth client (`booking-dev-local`) is in
  "Testing" publish mode, which requires every signing-in account to be
  added as an approved test user first (Google Cloud Console → APIs &
  Services → OAuth consent screen → Test users) — `mielikkix@gmail.com` had
  to be added there before this worked.

**Current gaps vs. this file's original plan below** (all explicitly
deferred, matching the instructions doc's own Section 20 priority order —
multi-tenant/entitlement work comes after booking/chat/demo/voice, not
before): no per-tenant OAuth (still one Mielikkix-owned calendar for
everyone), no dashboard "Bookings" tab, no `booking_enabled` plan
entitlement, no Voice Receptionist/Support Triage handoff (Phase 4), no
NL-parsing time-of-day filtering ("afternoon" is accepted but not filtered
on), no cancel/reschedule.

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
- **LLM**: `packages/agent-core`'s client, on Anthropic Claude Sonnet
  (`LLMClient(provider="anthropic")`, per `apps/agents/CLAUDE.md`'s tier
  assignment) — parses free-text requests into a structured query
  (`duration_minutes`, `earliest_date`, `latest_date`, `timezone`,
  `meeting_type`). This one call is shared infrastructure: both the
  standalone Booking Assistant entry points (chat widget, `/demo/
  booking-assistant`) AND Voice Receptionist's tool-calling loop funnel
  through it via `booking_service.resolve_booking_request()` — there is no
  separate "voice's own parsing" vs. "chat's own parsing."
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
   `packages/db`. (Currently: `app/models/booking.py`'s `Booking`, in
   `apps/api`'s own database, not yet `packages/db` — that package is still
   an empty scaffold; move this once per-tenant storage design work
   actually starts, per root `CLAUDE.md` convention #1.)

## Dashboard module

New "Bookings" tab in `apps/dashboard`, gated by entitlement: calendar/list
view of upcoming bookings, manual booking creation, cancellation.

## Development phases

1. **Phase 0 — Google Cloud OAuth client**: create a Google Cloud project,
   enable the Calendar API, create an OAuth 2.0 Client ID ("Web
   application") with this app's callback URL as an authorized redirect
   URI, connect one real test calendar through the OAuth flow to confirm it
   works end to end.
2. **Phase 1 — DONE.** `google_calendar_client.py` (now behind the
   `CalendarProvider` interface, `calendar_provider.py`) + `GET
   /api/agents/booking/dev/busy` against one hardcoded connected calendar.
3. **Phase 2 — DONE.** The agent-core-backed parser (`_parse_request` in
   `agents_booking.py`) turns free text into the structured slot query;
   business-hours-minus-busy availability math lives in
   `_available_slots_for_range`. Config-driven Mon-Fri hours
   (`settings.booking_agent_hours_start/_end`) stand in for a real
   per-tenant `BusinessSettings.business_hours` lookup, which needs
   per-tenant resolution (Phase 5) to mean anything yet.
4. **Phase 3 — DONE.** Real booking creation (`POST
   /api/agents/booking/confirm`), persisted (`Booking` model) and notified
   (`notify_new_booking`) — see "Current state" above.
5. **Phase 4 — Agent handoff**: build `create_booking(...)` for Voice
   Receptionist and Support Triage to call; test it with a fake caller. Not
   started — the chat-widget handoff (see "Current state" above) is a
   *different* handoff (chatbot → this agent's public HTTP routes), not
   this one (agent-to-agent direct function call).
6. **Phase 5 — Chat widget + dashboard OAuth UI**: the **chat widget** half
   of this is done (see "Current state" above) — though earlier than
   originally planned here, and against Mielikkix's own demo calendar
   rather than a real tenant's, since the live-demo goal (doc Section 14)
   needed it working before full per-tenant OAuth exists. The **dashboard
   OAuth UI** half (a real "Connect Google Calendar" button, replacing the
   one hardcoded calendar with genuine per-business OAuth) is not started.
7. **Phase 6 — Deploy**: wire into the shared modular agent process behind
   Caddy at `api.mielikkix.ai/api/agents/booking/...`.
8. **Phase 7 — Tests**: NL-parsing edge cases (ambiguous dates, past dates,
   unsupported durations) and the Google Calendar client against a mocked
   API (never a real Google account in tests).

## Definition of done for the 8-day sprint

- [ ] A business can connect their Google Calendar via OAuth from the
      dashboard (still one Mielikkix-owned demo calendar for everyone)
- [x] Availability lookup works against a real connected calendar
- [x] Booking created end-to-end from the Chat Widget flow
- [ ] Booking created end-to-end from a Voice Receptionist handoff
- [ ] Booking created end-to-end from a Support Triage handoff
- [x] Reminder sent ahead of the appointment (Google's own default event
      reminders — not a custom reminder schedule we configured ourselves)
- [x] NL parser asks a clarifying question rather than guessing on
      ambiguous/relative dates ("next Tuesday", "sometime this week")
- [x] Double-booking impossible — availability re-checked at confirmation
      time, not just at search time
- [ ] Bookings visible in dashboard, gated correctly by entitlement
- [ ] Deployed on the VPS, smoke-tested in production
