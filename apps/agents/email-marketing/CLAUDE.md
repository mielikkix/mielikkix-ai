# CLAUDE.md — apps/agents/email-marketing

Place this file at `mielikkix-ai/apps/agents/email-marketing/CLAUDE.md`.

## What this agent does

Writes and sends newsletters and promo campaigns to a business's own
contacts (its `Lead` records — `apps/api/app/models/lead.py`), on request or
on a schedule. A human reviews/approves each campaign before it sends —
this agent never emails a tenant's list unsupervised. Queued agent,
fast-follow after the 3 flagships (see root `CLAUDE.md`'s "Current
status").

## Integrations needed

- **Copywriting**: `packages/agent-core`'s LLM client only.
- **Sending**: `apps/api/app/notifications` (Resend provider, already
  wired) — do not add a second email-sending integration. Bulk/campaign
  sends are a different usage pattern from the transactional emails that
  module already sends (password reset, lead notifications), so this agent
  may need a batch-send helper added to that module rather than looping one
  email at a time — add it there, not a parallel client here (root
  `CLAUDE.md` convention #1's spirit: shared plumbing lives in one place).
- **Cart recovery**: needs an actual "cart abandoned" event to react to,
  which doesn't exist in this product yet (no checkout/cart concept beyond
  `Product` records today). Scope the first version to newsletters/promos
  only; cart recovery is a real campaign type in the data model below, but
  not buildable until that event exists upstream.

## Data this agent stores

```
Campaign
  id, business_id, type (newsletter | promo | cart_recovery),
  subject, body, status (draft | scheduled | sending | sent),
  scheduled_for, sent_at

CampaignSend
  id, campaign_id, lead_id, sent_at, opened_at (nullable — only if Resend
  reports opens for this account tier)
```

## Real-time or batch?

Drafting is request/response. Actual sends are batch/scheduled work through
the shared job queue (root `CLAUDE.md`) — sending to a whole contact list
is not something to do inline on an HTTP request.

## Dashboard module

New "Email Marketing" tab in `apps/dashboard`, gated by entitlement: draft a
campaign, edit/approve the generated copy, pick recipients (all leads or a
filtered subset), schedule or send now, and basic send stats (sent count,
opens if available).

## Definition of done for the 8-day sprint

- [ ] Campaign copy drafted from a plain-language brief
- [ ] Human can edit a draft before approving it
- [ ] Approved campaign actually sends to the business's real lead list via
      Resend
- [ ] A campaign can be scheduled for later, not just sent immediately
- [ ] Campaigns/send stats visible in dashboard, gated correctly by
      entitlement
- [ ] Deployed on the VPS, smoke-tested in production
