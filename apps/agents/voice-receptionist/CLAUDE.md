# CLAUDE.md — apps/agents/voice-receptionist

Place this file at `mielikkix-ai/apps/agents/voice-receptionist/CLAUDE.md`.

## What this agent does

Answers inbound calls to a business, holds a natural voice conversation grounded in
that business's info (via agent-core's RAG layer), books appointments or takes a
message, and texts/emails the business owner a summary. Flagship agent — first of the
10 to build.

## Integrations needed

- **Telephony**: a provider that can receive/forward calls and stream audio (e.g. Twilio
  Voice or equivalent) — confirm which provider before starting; this is the one
  external dependency that isn't "just an LLM call."
- **Speech-to-text / text-to-speech**: external API (not self-hosted) — pick one, wire
  it through `packages/agent-core`'s LLM client pattern so usage/cost logging is
  consistent with the rest of the platform.
- **Booking Assistant handoff**: when a caller wants to book, hand off to
  `apps/agents/booking-assistant` rather than re-implementing scheduling here.
- **SMS/email summary**: reuse whatever notification channel `apps/api` already has for
  the Chat Widget's lead-capture emails — do not stand up a second notification system.

## Data this agent stores

- Call log (caller number if available, duration, transcript, outcome).
- Summary sent to the business owner.
- Link to any booking/lead created as a result of the call.

All of this lives in `packages/db` under this tenant's data — no separate database.

## This is the one agent that behaves differently from the rest

Every other Force agent is request/response or scheduled/batch work. This one holds a
**sustained real-time connection** for the length of a phone call. Load-test it
separately from the others before assuming the VPS headroom that works for the other
9 agents applies here too (see the architecture plan's VPS resource notes).

## Dashboard module

New "Calls" tab in `apps/dashboard`, gated by this agent's entitlement: call log list,
transcript view, summary. Reuses `packages/ui` components — do not build one-off UI.

## Definition of done for the 8-day sprint

- [ ] Inbound call answered, held, and ended cleanly (happy path)
- [ ] Booking handoff to Booking Assistant works end-to-end
- [ ] Summary notification delivered to business owner
- [ ] Call log visible in dashboard, gated correctly by entitlement
- [ ] Load test: N concurrent calls sustained without dropping (define N with real target)
- [ ] Deployed on the VPS, smoke-tested in production
