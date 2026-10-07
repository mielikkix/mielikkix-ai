# CLAUDE.md — apps/agents (Force agent shared conventions)

Read the root `CLAUDE.md` first (non-negotiable monorepo conventions — shared
packages, one dashboard, modular-process deploy). This file adds the
conventions shared across the 6 Force agents built so far: **Voice
Receptionist**, **Booking Assistant**, **Support Triage** (the original 3
flagships), plus **Review & Reputation**, **SEO Audit & Optimize** (grew out
of the SEO Copywriter) and **Email Marketing** — see each agent's own
`CLAUDE.md` for exact status. The remaining agents (social-media,
feedback-survey, loyalty-reengage, quote-invoice) are still queued,
structure-only scaffolds built from `_template/`.

**Where the code is:** every built agent runs inside `apps/api` — routers in
`apps/api/app/api/agents_*.py` (plus `campaigns.py` and the `*_oauth.py`
connection routers), logic in `apps/api/app/services/`, models in
`apps/api/app/models/`, tests in `apps/api/tests/`. The `apps/agents/<name>/`
folders hold the spec/status doc and a stub `app/main.py` only.

Each agent's own `CLAUDE.md` (in its folder) covers what's specific to that
agent. This file covers what they share, so it isn't reinvented differently
in each one.

## Shared conventions

- **Language/runtime**: Python 3.12, FastAPI. Each agent's business logic
  lives in its own `apps/agents/<name>/`, but nothing here stands up its own
  server process, database, or subdomain — see "Process & deploy" below.
- **LLM**: `packages/agent-core`'s `LLMClient` — called **only** through it,
  never a per-agent `llm_client.py` (root convention #1). Multi-provider as
  of the Groq-rate-limiting incident (Groq alone kept stalling live voice
  turns for a minute-plus under real load — see `llm_client.py`'s own
  comments): each agent picks its own provider explicitly at construction
  (`LLMClient(provider="openai"|"anthropic"|"groq", ...)`), by tier —
    - **Voice Receptionist, SEO Audit & Optimize, Review & Reputation** (low-latency /
      cheap, routine generation) → **OpenAI**
      (`settings.openai_model`/`openai_mini_model`).
    - **Booking Assistant, Support Triage** (multi-turn reasoning,
      structured tool use) → **Anthropic Claude Sonnet**
      (`settings.anthropic_model`).
    - **Claude Opus** (`settings.anthropic_opus_model`) is available for a
      future workflow that genuinely needs deeper reasoning — nothing is
      assigned to it by default; don't reach for it without a real need.
  `DEFAULT_LLM_PROVIDER=groq` (root `.env`) is still what an agent gets if
  it constructs `LLMClient()` with no explicit `provider=` — Groq remains
  fine for anything low-stakes/latency-insensitive, just isn't assumed as
  the default for these four anymore. If agent-core is missing something
  (a new provider, a structured-output helper), add it there first, then
  consume it — never duplicate provider plumbing per agent.
- **Database**: the existing shared Postgres (`packages/db`, the `db`
  compose service, pgvector-enabled) — not a new database per agent. New
  tables carry `business_id` like every other tenant-scoped table.
- **Entitlements**: whether a tenant can use a given agent is checked once,
  by `apps/api/app/services/agent_access_service.require_agent_access`
  (`business_agent_access` table, switched on/off by a platform admin) — not
  re-implemented per agent (root convention #2). `packages/billing` is still
  a scaffold; this is meant to move there.
- **AI safety**: customer-facing prompts append
  `mielikkix_agent_core.guardrails.AI_SAFETY_RULES`; give every `LLMClient` a
  `usage_tag` so its calls show on the admin AI Usage page.
- **Per-tenant connections**: OAuth with a signed `state`, token encrypted
  via `core/encryption.py`, one row per business (`calendar_connections`,
  `review_connections`, `seo_google_connections`, `mailchimp_connections`).
- **Notifications (SMS/email)**: reuse `apps/api/app/notifications`
  (Resend provider already wired there) for summaries/escalations/reminders.
  Don't add a second Resend integration per agent.
- **Testing**: `pytest` + FastAPI's `TestClient`, same as `apps/api`.
- **Secrets**: the one root `.env` (git-ignored) — no per-agent `.env`/
  `.env.example`; add new keys to the root `.env.example`.

### Third-party services that legitimately stay separate

Two integrations are genuinely external products, not agent logic, so they
keep their own footprint rather than folding into agent-core:

- **Twilio** (Voice Receptionist's telephony) — a real PSTN phone number
  isn't something self-hosted software can provide; Twilio's API is the
  external dependency here, wired through the voice agent's own
  `integrations/` module.
- **Google Calendar** (Booking Assistant's calendar backend) — each
  business connects its own Google account via OAuth from `apps/dashboard`;
  the agent itself owns availability math and booking creation, calling
  Google only for `freebusy.query` / `events.insert`. Wired through the
  calendar-provider abstraction (`apps/api/app/integrations/
  calendar_provider.py` → `google_calendar_client.py`), so Outlook etc. is
  a factory change. Nothing to self-host. (Self-hosted Cal.com was the
  original plan and was dropped — see `booking-assistant/CLAUDE.md`'s "Why
  Google Calendar directly (not Cal.com)".)

## Process & deploy

Root convention #4: modular process, not one container per agent. Concretely:

- Every agent is a set of routers inside the one `apps/api` FastAPI process
  (`backend` service in `docker-compose.yml`), not one container each.
- Public routes are exposed under the existing `api.mielikkix.ai` host as
  path-scoped routes (e.g. `/api/agents/voice/incoming`,
  `/api/agents/booking/...`, `/api/agents/support/chat/message`) — not a new
  subdomain per agent, behind the same TLS reverse proxy as everything else
  (`files/ARCHITECTURE.md` §5).
- **Voice Receptionist is the one exception to "just a router"**: it holds a
  sustained real-time connection for the length of a phone call, unlike the
  other two (request/response). Load-test it separately before assuming the
  VPS headroom that works for the other agents applies here too.
- Background/non-real-time work is meant for the shared job queue in the
  root `CLAUDE.md`, which doesn't exist yet. Today: FastAPI `BackgroundTasks`
  (emails, SEO audits, crawls, website deploys) and one in-process
  APScheduler tick (SEO recurring audits). No standalone daemons.

## How the agents talk to each other

Because they share one process, a handoff between agents is a **direct
function/service call**, not an authenticated HTTP call between containers
— no `INTERNAL_API_KEY`, no internal network, one less thing to secure.
All of these are built:

- Voice Receptionist → `booking_service.resolve_booking_request` /
  `confirm_booking_slot`, when a caller wants to schedule something
- Voice Receptionist → `support_service.create_ticket`, when a caller has an
  issue that needs human follow-up
- Support Triage and the Chat Widget → the Booking Assistant flow, when a
  visitor asks to book (`suggest_booking_flow` on the reply makes the widget
  open its booking UI, which calls `/api/agents/booking/request` + `/confirm`)

## Note for Claude Code, on every agent

The person maintaining this code is a senior frontend engineer
(Angular/TypeScript/C#, 16+ years) who is **new to Python**. When writing
code for any agent:

- Comment thoroughly, especially anywhere Python idioms diverge from typical
  TS/Angular patterns (decorators, type hints, `async`/`await` semantics,
  dependency injection via `Depends()`, Pydantic models vs. TS interfaces).
- Prefer explicit, readable code over clever one-liners or heavy
  metaprogramming.
- Build in the phased order given in each agent's own `CLAUDE.md` and commit
  at the end of each phase, so the maintainer can follow along as it grows.

## Worth flagging back to the site review

The Aug 22, 2026 site review noted `website/` (the marketing site, in this
same repo — not a separate repo) ran no live chat widget, only a static
mockup. **Resolved:** the site now runs Mielikkix's own product Chat Widget
on every page (`Layout.astro`, dogfooding), and Support Triage has its own
live demo at `/demo/support-triage` (`website/public/support-triage.js`).
Support Triage is a **different widget from the product's chat widget**
(`apps/dashboard/src/widget`, embedded on tenant businesses' own sites and on
mielikkix.ai) — don't confuse the two when reading either doc.
