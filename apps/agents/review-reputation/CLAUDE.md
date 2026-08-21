# CLAUDE.md — apps/agents/review-reputation

Place this file at `mielikkix-ai/apps/agents/review-reputation/CLAUDE.md`.

## What this agent does

Monitors a tenant's Google/Facebook reviews, drafts AI reply suggestions in the
business's voice, and (optionally, per tenant setting) auto-posts replies within
guardrails. Flagship agent — third of the 10 to build.

## Integrations needed

- **Review sources**: Google Business Profile API and Facebook Page reviews API — confirm
  API access/quota for both before building; these are third-party rate-limited APIs,
  not something agent-core already wraps.
- **Reply drafting**: uses `packages/agent-core`'s LLM client — no separate LLM
  integration here.
- **Auto-post guardrails**: never auto-post a reply to a review below a configurable
  star-rating threshold without human approval — this must be enforced in code, not
  just documented.

## Data this agent stores

- Synced reviews (source, rating, text, timestamp).
- Draft/sent replies, and whether each was auto-posted or human-approved.
- Per-tenant auto-post threshold setting.

## Polling design note

This agent is scheduled/batch work (poll on an interval), not real-time — it belongs in
the shared job queue described in the root CLAUDE.md, not a standing daemon.

## Dashboard module

New "Reviews" tab in `apps/dashboard`, gated by entitlement: review inbox, draft reply
approval flow, auto-post threshold setting.

## Definition of done for the 8-day sprint

- [ ] Reviews sync from at least one source (Google or Facebook) on a schedule
- [ ] AI draft reply generated for a new review
- [ ] Human-approval flow works in dashboard
- [ ] Auto-post threshold enforced correctly (test both above and below threshold)
- [ ] Reviews/drafts visible in dashboard, gated correctly by entitlement
- [ ] Deployed on the VPS, smoke-tested in production
