# apps/agents/seo-audit

Built and live — the SEO Audit & Optimization agent (folder renamed from
`seo-copywriter` once its scope grew past copywriting alone). Crawls a
business's website(s) for technical/on-page SEO issues, turns findings into
a prioritized action plan and client-ready report, and still bulk-generates
product descriptions and SEO metadata into a separate `SeoDraft` table
(the original Copywriter, Part 1 of this agent's `CLAUDE.md`), reviewed and
approved by a human in the dashboard before overwriting anything live.

Sold in two tiers — free "SEO Audit & Optimize" and paid "Professional SEO
Audit & Optimization" (29 901 kr) — see `app/core/agent_catalog.py`.

See [`CLAUDE.md`](./CLAUDE.md) in this directory for integrations needed,
data model, and test criteria — read that before touching this agent's code.
