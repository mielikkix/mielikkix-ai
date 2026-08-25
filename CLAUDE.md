# CLAUDE.md — mielikkix-ai

Place this file at the **root of the `mielikkix-ai` repo**.

## What this repo is

Monorepo for the Mielikkix AI product platform: the live Chat Widget, the customer
dashboard, the core API, the 10 Mielikkix Force AI agents, **and** the public
marketing site (`website/`) — kept in this same repo deliberately, so that adding
AI-agent promotion pages to the marketing site later has full context on the
product/agents right alongside it, rather than being split across two repos.

## Structure

```
mielikkix-ai/
├── apps/
│   ├── chat-widget/     # LIVE product. Embeddable widget: RAG-grounded Q&A, lead capture.
│   ├── dashboard/       # app.mielikkix.ai — ONE multi-tenant app for every customer.
│   │                     Renders only the modules a tenant is entitled to (packages/billing).
│   ├── api/             # core backend (was backend/): auth, chat logic, agent orchestration.
│   └── agents/
│       ├── CLAUDE.md             # shared conventions for the 3 active flagship agents
│       ├── voice-receptionist/   # flagship — see its own CLAUDE.md
│       ├── booking-assistant/    # flagship — see its own CLAUDE.md
│       ├── support-triage/       # flagship — see its own CLAUDE.md
│       ├── review-reputation/    # queued (was flagship 3; superseded by support-triage — see apps/agents/CLAUDE.md)
│       ├── _template/            # copy this folder to start any of the remaining queued agents
│       └── ...                   # social-media, email-marketing, seo-copywriter,
│                                  # feedback-survey, loyalty-reengage, quote-invoice
├── packages/
│   ├── agent-core/      # shared LLM client, prompt/tool-calling framework, memory/RAG.
│   │                     Every agent imports this — do not reimplement LLM plumbing per agent.
│   ├── billing/         # subscription + entitlement logic (individual / 3-pack / Full Crew).
│   │                     Gates BOTH api/ access and what dashboard/ renders per tenant.
│   ├── db/               # shared schema/models, multi-tenant data layer.
│   ├── auth/             # shared session/auth logic.
│   └── ui/               # shared UI components used by dashboard/ (and chat-widget/'s own UI).
├── infra/
│   ├── docker-compose.yml
│   ├── docker/           # one Dockerfile per app/agent
│   └── deploy/           # CI/CD + per-env config
├── website/              # mielikkix.ai marketing site — Astro, own stack/CLAUDE.md/ARCHITECTURE.md.
│                          # Static build → Hostinger shared hosting, separate from the VPS apps run on.
│                          # Product/agent AI-promotion pages get added here as they ship.
├── files/
├── .claude/
└── .env*, .gitignore
```

## Non-negotiable conventions

1. **Never duplicate LLM/agent plumbing inside an individual agent folder.** If an agent
   needs something agent-core doesn't have yet, add it to agent-core first, then consume it.
2. **Entitlements are checked in `packages/billing`, nowhere else.** Both `apps/api` routes
   and `apps/dashboard` module rendering must call the same entitlement check — do not
   hand-roll a second gate.
3. **No per-customer or per-agent dashboards.** `apps/dashboard` is one app for every
   tenant; new agent UI is a new module inside it, gated by entitlement, not a new app.
4. **Deploy as a modular process, not one container per agent.** The target VPS is a
   2 vCPU / 8GB box — see `infra/deploy/README.md` for the resource budget. Background
   work (emails, review polling, non-real-time tasks) goes through the shared job queue,
   not a standalone always-on daemon per agent.
5. **All 10 agents call external LLM/STT/TTS APIs.** No self-hosted models on this VPS.

## Current status

- Chat Widget: **live**, in production.
- Dashboard: **live**, serving the Chat Widget module today; agent modules added as they ship.
- Force agents: flagship 3 (Voice Receptionist, Booking Assistant, Support Triage)
  in active build — see `apps/agents/CLAUDE.md` for shared conventions across
  the three. Review & Reputation (originally the third flagship) and the
  remaining 6 are queued as fast-follow using the same `_template/` pattern.

## Where to look next

- Architecture rationale and per-agent specs: `Mielikkix_10_Agent_Architecture_Plan.docx`
  (project docs).
- Day-by-day build plan: `Mielikkix_8Day_ToDo.docx`.
- Each agent folder has its own `CLAUDE.md` with that agent's specific integrations,
  data model, and test criteria — read that before touching an agent's code.
