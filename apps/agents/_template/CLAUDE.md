# CLAUDE.md — apps/agents/_template

Copy this folder to `mielikkix-ai/apps/agents/<agent-name>/` to start any new
agent, and fill in every `<...>` below before writing code. The 6 queued
agents in the reference table below already have their own scaffolded
folder (built from this template) — use this template again only if a
brand-new agent gets added to the roster.

## What this agent does

<one paragraph: input, what it does, output>

## Integrations needed

<list every external API/service this agent needs, beyond what packages/agent-core
already provides. If it needs nothing beyond agent-core, say so explicitly — that's a
sign this agent should be fast to build.>

## Data this agent stores

<list the tables/records this agent adds to packages/db>

## Real-time or batch?

<Most of the queued agents are batch/scheduled work (like Review & Reputation)
rather than real-time (like Voice Receptionist) — say which this is, since that
decides whether it runs through the shared job queue or needs its own handling.>

## Dashboard module

<New tab name in apps/dashboard, gated by this agent's entitlement, and what it shows.>

## Definition of done

- [ ] <core happy-path flow works end-to-end>
- [ ] <dashboard module shows correct data, gated correctly by entitlement>
- [ ] <any agent-to-agent handoff, if applicable>
- [ ] Deployed on the VPS, smoke-tested in production

---
### Reference — the 6 queued agents already scaffolded from this template

| Agent | Folder | One-line scope |
|---|---|---|
| Social Media Agent | `apps/agents/social-media` | Turns offers/updates into ready-to-post social content |
| Email Marketing | `apps/agents/email-marketing` | Newsletters, cart recovery, promo sends |
| SEO Copywriter | `apps/agents/seo-copywriter` | Bulk product descriptions & metadata |
| Feedback & Survey | `apps/agents/feedback-survey` | Post-visit surveys, sentiment summaries |
| Loyalty & Re-engagement | `apps/agents/loyalty-reengage` | Automated win-back and repeat-customer offers |
| Quote & Invoice | `apps/agents/quote-invoice` | Turns a customer request into a formal quote/invoice |

(Support Triage is the third flagship, not queued — see
`apps/agents/support-triage/CLAUDE.md`, built directly rather than from this
template's placeholder shape.)
