# CLAUDE.md — apps/agents/voice-receptionist

Read `apps/agents/CLAUDE.md` first (shared conventions across the three
flagship agents) — this file covers only what's specific to this one.

## What this agent does

Answers inbound calls to a business via a real phone number, holds a
natural spoken conversation grounded in that business's info (via
`packages/agent-core`'s RAG layer), can hand off mid-call to Booking
Assistant or Support Triage, and texts/emails the business owner a summary
when the call ends. Flagship agent — first of the 10 to build.

## Why Twilio

Real PSTN phone numbers aren't something open-source software can provide on
its own — a telephony carrier has to be in the loop. Twilio was chosen (over
self-hosting Asterisk) because this ships to real businesses and Twilio
gets you a working, reliable number today with speech-to-text/text-to-speech
already built into its API (`<Gather input="speech">`, `<Say>`), instead of
running your own PBX. Everything *around* the call — conversation logic,
LLM, booking/ticket handoff — is your own code, routed through agent-core.

## How a Twilio voice call actually works (context for a Python newcomer)

Twilio doesn't run your code — it calls *your server* over HTTP each time
something happens on the call, and expects back a small XML document called
**TwiML** telling it what to do next (speak something, listen for speech,
hang up, etc.). Think of it like a simple state machine driven by webhooks,
similar to how Stripe drives your server via callbacks rather than holding a
persistent connection open.

1. Someone calls the number → Twilio sends `POST /api/agents/voice/incoming`
2. Server replies with TwiML: `<Say>` a greeting, then
   `<Gather input="speech">` to listen
3. When the caller stops talking, Twilio sends the transcribed text to
   `POST /api/agents/voice/gather`
4. Server decides what to say next (via the LLM, through agent-core), replies
   with more TwiML, and the loop continues
5. When the call ends, Twilio hits a status callback — that's the cue to
   generate and send the summary

## Integrations needed

- **Telephony**: Twilio (`twilio` official Python SDK) — receiving call
  webhooks, building TwiML responses, sending the summary SMS. This is the
  one external dependency that isn't "just an LLM call," and it's specific
  to this agent (not shared via agent-core).
- **LLM**: `packages/agent-core`'s client — the conversational brain and the
  intent classifier (function-calling schema: `book_appointment`,
  `support_issue`, `general_question`, `leave_message`).
- **Booking Assistant handoff**: direct call into
  `apps/agents/booking-assistant`'s booking service (see
  `apps/agents/CLAUDE.md` — same process, no internal HTTP hop) when a
  caller wants to book.
- **Support Triage handoff**: direct call into
  `apps/agents/support-triage`'s ticket service when a caller has an issue
  needing human follow-up.
- **SMS/email summary**: `apps/api/app/notifications` (Resend provider) —
  do not stand up a second notification system.

## Data this agent stores

- Call log (caller number if available, duration, transcript, outcome).
- Summary sent to the business owner.
- Link to any booking/ticket created as a result of the call.

All in `packages/db`, scoped to the tenant — no separate database.

## Security

- **Validate every Twilio webhook** with
  `twilio.request_validator.RequestValidator` and the `X-Twilio-Signature`
  header — without this, anyone who finds the webhook URL can pretend to be
  Twilio.
- Rate-limit the `/api/agents/voice/*` routes.
- **Two-party consent laws vary by country/state** for recording calls — the
  greeting must disclose an AI assistant is handling the call before
  anything is recorded/transcribed. This is a legal/compliance decision, not
  something to hardcode without checking local requirements for the
  businesses being sold to.

## This is the one agent that behaves differently from the rest

Every other Force agent is request/response or scheduled/batch work. This
one holds a **sustained real-time connection** for the length of a phone
call. Load-test it separately from the others before assuming the VPS
headroom that works for the rest applies here too (see
`apps/agents/CLAUDE.md` — "Process & deploy").

## Dashboard module

New "Calls" tab in `apps/dashboard`, gated by this agent's entitlement: call
log list, transcript view, summary. Reuses `packages/ui` components — do not
build one-off UI.

## Development phases

1. **Phase 0 — Twilio sandbox**: trial account + number; `ngrok` (or
   `cloudflared tunnel`) to expose the local server for webhook testing; a
   bare `<Say>Hello world</Say>` working end-to-end on a real call.
2. **Phase 1 — Skeleton**: `/api/agents/voice/incoming` +
   `.../gather` routes, first LLM-generated response via agent-core (no
   intent routing yet, just a friendly echo/conversation).
3. **Phase 2 — Intent + FAQ**: add the intent classifier and FAQ answering
   grounded in the business's data via agent-core's RAG layer.
4. **Phase 3 — Booking handoff**: wire the direct call into Booking
   Assistant's service (stub it locally if that agent isn't built yet).
5. **Phase 4 — Support handoff**: wire the direct call into Support
   Triage's ticket service.
6. **Phase 5 — Wrap-up**: call summary generation, transcript/summary
   persistence, SMS + optional email via the shared notification channel.
7. **Phase 6 — Deploy**: wire into the shared modular agent process behind
   Caddy, point the Twilio number's webhook at the production URL.
8. **Phase 7 — Tests + hardening**: pytest coverage for the webhook handlers
   and conversation state; basic structured logging.

## Definition of done for the 8-day sprint

- [ ] Inbound call answered, held, and ended cleanly (happy path)
- [ ] Webhook signature validation rejects forged requests
- [ ] Booking handoff to Booking Assistant works end-to-end
- [ ] Support handoff to Support Triage works end-to-end
- [ ] Summary notification delivered to business owner
- [ ] Graceful fallback TwiML if the LLM call fails/times out mid-call
      (never leave the caller in dead air)
- [ ] Call log visible in dashboard, gated correctly by entitlement
- [ ] Load test: N concurrent calls sustained without dropping (define N
      with a real target)
- [ ] Deployed on the VPS, smoke-tested in production
