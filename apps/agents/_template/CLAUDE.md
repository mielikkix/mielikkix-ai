# CLAUDE.md — apps/agents/_template

Copy this folder to `mielikkix-ai/apps/agents/<agent-name>/` to start any of the
remaining 7 agents, and fill in every `<...>` below before writing code.

## What this agent does

<one paragraph: input, what it does, output>

## Integrations needed

<list every external API/service this agent needs, beyond what packages/agent-core
already provides. If it needs nothing beyond agent-core, say so explicitly — that's a
sign this agent should be fast to build.>

## Data this agent stores

<list the tables/records this agent adds to packages/db>

## Real-time or batch?

<Most of the remaining 7 are batch/scheduled work (like Review & Reputation) rather
than real-time (like Voice Receptionist) — say which this is, since that decides
whether it runs through the shared job queue or needs its own handling.>

## Dashboard module

<New tab name in apps/dashboard, gated by this agent's entitlement, and what it shows.>

## Definition of done

- [ ] <core happy-path flow works end-to-end>
- [ ] <dashboard module shows correct data, gated correctly by entitlement>
- [ ] <any agent-to-agent handoff, if applicable>
- [ ] Deployed on the VPS, smoke-tested in production

---
### Reference — the remaining 7 agents this template covers

| Agent | One-line scope |
|---|---|
| Support Triage | Sorts inbound support tickets, drafts replies, escalates when needed |
| Social Media Agent | Turns offers/updates into ready-to-post social content |
| Email Marketing | Newsletters, cart recovery, promo sends |
| SEO Copywriter | Bulk product descriptions & metadata |
| Feedback & Survey | Post-visit surveys, sentiment summaries |
| Loyalty & Re-engagement | Automated win-back and repeat-customer offers |
| Quote & Invoice | Turns a customer request into a formal quote/invoice |
