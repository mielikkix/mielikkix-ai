# CLAUDE.md — apps/agents/seo-copywriter

Place this file at `mielikkix-ai/apps/agents/seo-copywriter/CLAUDE.md`.

## What this agent does

Bulk-generates product descriptions and SEO metadata (title tag, meta
description) for a business's existing product catalog
(`apps/api/app/models/product.py`), written to actually target real search
intent rather than keyword-stuffed filler. A human reviews and approves
each draft before it overwrites anything live. Queued agent, fast-follow
after the 3 flagships (see root `CLAUDE.md`'s "Current status").

## Integrations needed

Nothing beyond `packages/agent-core`'s LLM client — this agent reads an
existing `Product` row and writes a draft back; no third-party API, no
external account setup. One of the faster agents to build for exactly this
reason.

## Data this agent stores

```
SeoDraft
  id, product_id, draft_description, draft_seo_title, draft_meta_description,
  status (draft | approved | rejected), created_at
```

Deliberately a separate draft table, not a direct write to `Product` —
generating in bulk across a whole catalog and silently overwriting live,
customer-facing copy without review is the one failure mode this agent
must never have.

## Real-time or batch?

Batch: "generate for this whole catalog" (or a selected subset) is the
core action, run through the shared job queue (root `CLAUDE.md`) rather
than generating N products synchronously on one request.

## Dashboard module

New "SEO" tab in `apps/dashboard`, gated by entitlement: pick which
products to (re)generate for, a before/after diff view per product, and an
approve action that copies the draft onto the real `Product` record.
`Product` (`apps/api/app/models/product.py`) already has `description`;
`seo_title`/`meta_description` don't exist on it yet — adding those two
columns is part of this agent's own build, not a prerequisite someone else
needs to do first.

## Definition of done for the 8-day sprint

- [ ] Bulk-generate drafts for a selected set of products in one action
- [ ] Before/after diff view lets a human compare draft vs. live copy
- [ ] Approving a draft updates the real `Product` record; rejecting
      discards it without touching live data
- [ ] Drafts visible in dashboard, gated correctly by entitlement
- [ ] Deployed on the VPS, smoke-tested in production
