# CLAUDE.md — apps/agents/feedback-survey

Place this file at `mielikkix-ai/apps/agents/feedback-survey/CLAUDE.md`.

## What this agent does

Sends a short post-interaction survey after a booking or a resolved support
ticket, then summarizes the responses into plain-language sentiment
summaries — no spreadsheet of raw responses for the business owner to read
through themselves. Queued agent, fast-follow after the 3 flagships (see
root `CLAUDE.md`'s "Current status").

## Integrations needed

- **Sentiment summarization**: `packages/agent-core`'s LLM client only.
- **Sending**: `apps/api/app/notifications` (Resend provider, already
  wired) — do not add a second email integration.
- **Trigger sources**: Booking Assistant (after an appointment completes)
  and Support Triage (after a ticket resolves) each call this agent's
  `request_feedback(...)` directly (same process, same
  direct-function-call shape `apps/agents/CLAUDE.md` describes for the
  other handoffs — just inbound to this agent instead of outbound from it).
  Both of those agents' own `CLAUDE.md`s should get a one-line note added
  when this agent is actually built, the same way Booking Assistant's and
  Support Triage's CLAUDE.md's already reference calling into each other.

## Data this agent stores

```
Survey
  id, business_id, trigger_source (booking | ticket), trigger_id
  (the booking/ticket this survey is about), sent_at, response_text,
  rating (nullable), sentiment (positive | neutral | negative), summary
```

## Real-time or batch?

Sending is event-triggered (fires when a booking/ticket completes, through
the shared job queue rather than inline in that agent's own request/response
path — a slow email send should never make the booking/ticket-resolution
response wait on it). Sentiment summarization/digests are batch, on a
schedule (e.g. weekly).

## Dashboard module

New "Feedback" tab in `apps/dashboard`, gated by entitlement: response list
with sentiment tags, a sentiment trend over time, and a plain-language
weekly digest.

## Definition of done for the 8-day sprint

- [ ] Survey sends automatically after a booking completes
- [ ] Survey sends automatically after a support ticket resolves
- [ ] A response gets a sentiment tag and rolls into a summary
- [ ] Responses/trend visible in dashboard, gated correctly by entitlement
- [ ] Deployed on the VPS, smoke-tested in production
