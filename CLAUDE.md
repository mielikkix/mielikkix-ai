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
│   ├── chat-widget/     # README-only placeholder. The LIVE widget (RAG Q&A, lead capture,
│   │                     booking) is built from apps/dashboard/src/widget into widget.js.
│   ├── dashboard/       # app.mielikkix.ai — ONE multi-tenant app for every customer (+ /admin).
│   │                     Renders only the modules a tenant is entitled to.
│   ├── api/             # core backend (FastAPI): auth, chat/RAG, every agent's routes + services.
│   └── agents/                  # one folder per agent: its spec/status (CLAUDE.md) + a stub.
│       │                          # The running code for every built agent is in apps/api
│       │                          # (app/api/agents_*.py, campaigns.py + app/services/*).
│       ├── CLAUDE.md             # shared conventions for all Force agents
│       ├── voice-receptionist/   # built — see its own CLAUDE.md
│       ├── booking-assistant/    # built — see its own CLAUDE.md
│       ├── support-triage/       # built — see its own CLAUDE.md
│       ├── review-reputation/    # built — see its own CLAUDE.md
│       ├── seo-audit/            # SEO Audit & Optimize (incl. the original SEO Copywriter) — built
│       ├── email-marketing/      # built (Mailchimp) — see its own CLAUDE.md
│       ├── _template/            # copy this folder to start a new agent
│       └── ...                   # queued: social-media, feedback-survey,
│                                  # loyalty-reengage, quote-invoice
├── packages/
│   ├── agent-core/      # REAL: shared LLMClient (OpenAI/Anthropic/Groq), AI safety rules,
│   │                     usage hook. Every agent imports this — do not reimplement LLM plumbing.
│   ├── billing/         # TARGET home of subscription + entitlement logic — still a scaffold;
│   │                     today: apps/api/app/core/plans.py + services/agent_access_service.py.
│   ├── db/               # scaffold — models/migrations still in apps/api/app/models + alembic/.
│   ├── auth/             # scaffold — auth still in apps/api/app/core/security.py.
│   └── ui/               # scaffold — components still in apps/dashboard/src/shared.
├── infra/                # READMEs only so far (docker/, deploy/). docker-compose.yml is still
│                          # at the repo root; Dockerfiles live next to each app.
├── website/              # mielikkix.ai marketing site — Astro, own stack/CLAUDE.md/ARCHITECTURE.md.
│                          # Static build → Hostinger shared hosting, separate from the VPS apps run on.
│                          # Product/agent AI-promotion pages get added here as they ship.
├── docs/                 # BRAND.md, pricing-rules.md, privacy/ (GDPR records)
├── files/                # project docs: FEATURES, ARCHITECTURE, DATABASE_SCHEMA, LLM_MODELS, ...
├── .github/workflows/    # CI: API tests + migration check, dashboard + widget builds
├── .claude/
├── docker-compose.yml    # db (Postgres 16 + pgvector), backend (API), frontend (dashboard/nginx)
└── .env*, .gitignore
```

## Non-negotiable conventions

1. **Never duplicate LLM/agent plumbing inside an individual agent folder.** If an agent
   needs something agent-core doesn't have yet, add it to agent-core first, then consume it.
2. **Entitlements are checked in one place, nowhere else.** Both `apps/api` routes
   and `apps/dashboard` module rendering must use the same check — do not hand-roll a
   second gate. Today that one place is `apps/api/app/services/agent_access_service.py`
   (agents, `business_agent_access` table; the dashboard reads it via
   `GET /api/businesses/me/agents`) plus `services/plan_service.py` (Chat Widget plan
   limits). `packages/billing` is where it is meant to move.
3. **No per-customer or per-agent dashboards.** `apps/dashboard` is one app for every
   tenant; new agent UI is a new module inside it, gated by entitlement, not a new app.
4. **Deploy as a modular process, not one container per agent.** The target VPS is a
   2 vCPU / 8GB box. Background work (emails, review polling, non-real-time tasks) goes
   through the shared job queue, not a standalone always-on daemon per agent. That queue
   doesn't exist yet: today background work runs as FastAPI `BackgroundTasks`, plus one
   in-process APScheduler tick for SEO recurring audits (`services/seo_schedule_service.py`).
5. **All 10 agents call external LLM/STT/TTS APIs.** No self-hosted models on this VPS.
6. **Third-party integrations sit behind a provider abstraction, not spread through the app.**
   `apps/api/app/rag/providers/` (LLM/embeddings) and `apps/api/app/integrations/
   calendar_provider.py` (calendar) are the pattern: an ABC + a `get_*_provider()` factory,
   so swapping Groq/Gemini/Ollama or Google/Outlook is a factory change, not a rewrite.
   Already following it: `integrations/review_platforms/`, `integrations/email_marketing_providers/`,
   `notifications/` (console/Resend). New integrations (payments, SMS, etc.) follow the same shape.

## Current status (2026-10-07)

- Chat Widget: **live**, in production — multi-language, inline booking, AI notice/consent
  screen, soft conversation limit.
- Dashboard: **live**, English + Norwegian (Bokmål). Chat Widget pages plus agent modules
  (SEO, Reviews, Email Marketing) gated per business; `/admin` for the operator (businesses,
  agent access, AI usage, bookings, tickets, blog CMS).
- Force agents built (6 of 10):
  - **Voice Receptionist** — Twilio; Mielikkix's own number/demo, not per-tenant yet.
  - **Booking Assistant** — per-business Google Calendar OAuth + opening hours; reached from
    the Chat Widget, Voice and Support Triage.
  - **Support Triage** — live demo at mielikkix.ai/demo/support-triage (Mielikkix's own
    support; not per-tenant yet). The sitewide bubble on mielikkix.ai is the product Chat Widget.
  - **Review & Reputation** — per-business Google Business Profile connection, human-approved
    publishing.
  - **SEO Audit & Optimize** — free tier and paid **Start** tier (490 kr; key still
    `professional`), see `apps/agents/seo-audit/CLAUDE.md` and `app/core/agent_catalog.py`.
  - **Email Marketing** — per-business Mailchimp: draft → approve → send/schedule → report.
  See `apps/agents/CLAUDE.md` for shared conventions.
- Queued (4): Social Media, Feedback & Survey, Loyalty & Re-engagement, Quote & Invoice —
  start from `_template/`.
- GDPR: consent records, account export/deletion, visitor retention/erasure, legal pages.
- No payment processor yet: paid plans are set by a platform admin.
- Full feature list: `files/FEATURES.md`. Tech stack: `files/CLAUDE.md`.

## Where to look next

- **Target SaaS architecture (multi-tenant entitlements, calendar-provider abstraction,
  AI-agent-core intent routing, live-demo goals): `files/Mielikkix AI — Claude Code Project
  Instructions.md`.** Read this before any change that touches Booking Assistant, the
  chatbot's intent handling, or multi-tenant/billing structure — it's the authoritative
  reference for where this platform is headed, not just what exists today.
- Architecture rationale and per-agent specs: `Mielikkix_10_Agent_Architecture_Plan.docx`
  (project docs).
- Day-by-day build plan: `Mielikkix_8Day_ToDo.docx`.
- Each agent folder has its own `CLAUDE.md` with that agent's specific integrations,
  data model, and test criteria — read that before touching an agent's code.
- **Which LLM provider/model powers which feature, and why: `files/LLM_MODELS.md`.**
  Read before changing any agent's `_llm_client` construction or adding a new one —
  covers the Chat Widget's separate per-tenant provider system vs. the Force agents'
  explicit tier assignment (OpenAI cheap/fast vs. Anthropic Claude Sonnet vs. the
  reserved Opus tier), and exactly which env var controls which model.
