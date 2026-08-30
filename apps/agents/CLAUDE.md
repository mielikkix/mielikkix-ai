# CLAUDE.md — apps/agents (Force agent shared conventions)

Read the root `CLAUDE.md` first (non-negotiable monorepo conventions — shared
packages, one dashboard, modular-process deploy). This file adds the
conventions specific to the three flagship agents currently in active build:
**Voice Receptionist**, **Booking Assistant**, **Support Triage** (this
supersedes Review & Reputation as the third active flagship — see that
change noted in the root `CLAUDE.md`'s "Current status"; Review & Reputation
stays scaffolded and queued, not dropped).

Each agent's own `CLAUDE.md` (in its folder) covers what's specific to that
agent. This file covers what all three share, so it isn't reinvented
differently in each one.

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
    - **Voice Receptionist, SEO Copywriter, Review & Reputation** (low-latency /
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
  in `packages/billing` — not re-implemented per agent (root convention #2).
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
- **Cal.com, self-hosted** (Booking Assistant's scheduling engine) — a
  separate open-source app you didn't build, in its own container with its
  own Postgres (that's a different thing from "one container/DB per Force
  agent" — Cal.com isn't one of the 10 agents, it's a dependency of one).
  Runs at its own subdomain, e.g. `scheduling.mielikkix.ai`; set up event
  types via Cal.com's own admin UI.

## Process & deploy

Root convention #4: modular process, not one container per agent. Concretely
for these three:

- All three mount into the shared modular agent process (see
  `infra/deploy/README.md` — exact wiring still TBD, same placeholder status
  as the rest of `infra/deploy`), not one FastAPI container each.
- Public routes are exposed under the existing `api.mielikkix.ai` host as
  path-scoped routes (e.g. `/api/agents/voice/incoming`,
  `/api/agents/booking/...`, `/api/agents/support/chat/message`) — not a new
  subdomain per agent. Caddy (planned reverse-proxy/TLS layer, see
  `files/ARCHITECTURE.md` §5 — not yet configured) fronts the one host,
  same as everything else.
- **Voice Receptionist is the one exception to "just a router"**: it holds a
  sustained real-time connection for the length of a phone call, unlike the
  other two (request/response). Load-test it separately before assuming the
  VPS headroom that works for the other agents applies here too.
- Background/non-real-time work (escalation emails, reminders, review
  polling once that agent is built) goes through the shared job queue
  mentioned in the root `CLAUDE.md`, not a standalone daemon.

## How the three agents talk to each other

Because they share one process, a handoff between agents is a **direct
function/service call**, not an authenticated HTTP call between containers
— no `INTERNAL_API_KEY`, no internal network, one less thing to secure:

- Voice Receptionist → Booking Assistant's booking service, when a caller
  wants to schedule something
- Voice Receptionist → Support Triage's ticket service, when a caller has an
  issue that needs human follow-up
- Support Triage → Booking Assistant's booking service, when a chat visitor
  asks to book/reschedule

Each service exposes a plain importable function (e.g.
`booking_assistant.service.create_booking(...)`) for the others to call.

## Note for Claude Code, on every agent in this trio

The person maintaining this code is a senior frontend engineer
(Angular/TypeScript/C#, 16+ years) who is **new to Python**. When writing
code for any of these three:

- Comment thoroughly, especially anywhere Python idioms diverge from typical
  TS/Angular patterns (decorators, type hints, `async`/`await` semantics,
  dependency injection via `Depends()`, Pydantic models vs. TS interfaces).
- Prefer explicit, readable code over clever one-liners or heavy
  metaprogramming.
- Build in the phased order given in each agent's own `CLAUDE.md` and commit
  at the end of each phase, so the maintainer can follow along as it grows.

## Worth flagging back to the site review

The Aug 22, 2026 site review noted `website/` (the marketing site, in this
same repo — not a separate repo) runs no live chat widget, only a static
mockup. Support Triage's chat widget (see its own `CLAUDE.md`, Phase 4) is
the fix — once live, embed it site-wide in `website/` instead of the mockup.
This is a **different widget from the product's existing chat widget**
(`apps/dashboard/src/widget`, embedded on tenant businesses' own sites) —
don't confuse the two when reading either doc.
