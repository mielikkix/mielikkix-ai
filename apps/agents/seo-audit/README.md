# apps/agents/seo-audit

Built and live — the SEO Audit & Optimization agent (folder renamed from
`seo-copywriter` once its scope grew past copywriting alone). Crawls a
business's website(s) for technical/on-page SEO issues, turns findings into
a prioritized action plan and client-ready report, and still bulk-generates
product descriptions and SEO metadata into a separate `SeoDraft` table
(the original Copywriter, Part 1 of this agent's `CLAUDE.md`), reviewed and
approved by a human in the dashboard before overwriting anything live.

Sold in two tiers — free "SEO Audit & Optimize" and paid "SEO Audit & Optimize
Start" (490 kr/month: Google Analytics + Search Console, scheduled audits) — see
`app/core/agent_catalog.py`. All code lives in `apps/api` (`app/api/agents_seo*.py`,
`app/services/seo_*.py`, `app/services/web_crawl.py`); architecture overview in the
repo-root `ARCHITECTURE-NOTES.md`.

See [`CLAUDE.md`](./CLAUDE.md) in this directory for integrations needed,
data model, and test criteria — read that before touching this agent's code.
