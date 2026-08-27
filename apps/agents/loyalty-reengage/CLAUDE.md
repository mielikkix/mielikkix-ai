# CLAUDE.md — apps/agents/loyalty-reengage

Place this file at `mielikkix-ai/apps/agents/loyalty-reengage/CLAUDE.md`.

## What this agent does

Finds customers who haven't come back in a while (based on their booking
and lead history) and sends an automated win-back offer, without the
business owner having to notice the gap or write the email themselves.
Queued agent, fast-follow after the 3 flagships (see root `CLAUDE.md`'s
"Current status").

## Integrations needed

- **Offer copy**: `packages/agent-core`'s LLM client only.
- **Sending**: `apps/api/app/notifications` (Resend provider, already
  wired) — do not add a second email integration.
- **Inactivity detection**: reads existing `Lead`
  (`apps/api/app/models/lead.py`) and Booking Assistant's booking history
  (once that agent's own booking log exists — see its `CLAUDE.md`) to
  compute "last seen" per customer against a per-tenant inactivity
  threshold (e.g. "60 days since last booking"). No new external API —
  this is entirely derived from data already in `packages/db`.

## Data this agent stores

```
ReengagementRule
  id, business_id, inactivity_days (the per-tenant threshold), offer_template,
  is_active

ReengagementSend
  id, business_id, lead_id, sent_at
  -- one row per customer per campaign run, so the same inactive customer
  -- doesn't get re-sent the same win-back offer every time the batch job runs
```

## Real-time or batch?

Batch/scheduled: a periodic job (weekly, via the shared job queue in root
`CLAUDE.md`) scans for customers past the inactivity threshold who haven't
already received a `ReengagementSend` recently, and sends the offer.

## Dashboard module

New "Loyalty" tab in `apps/dashboard`, gated by entitlement: set the
inactivity threshold and offer template, view send history, and an opt-out
list (a customer who asks not to receive these must actually stop getting
them, not just be a UI toggle nobody wired to the send job).

## Definition of done for the 8-day sprint

- [ ] Inactivity threshold correctly identifies customers past the cutoff
- [ ] Win-back offer sends automatically on schedule, not manually triggered
- [ ] A customer never gets the same campaign sent twice in one run
- [ ] Opt-out actually prevents future sends to that customer
- [ ] Send history visible in dashboard, gated correctly by entitlement
- [ ] Deployed on the VPS, smoke-tested in production
