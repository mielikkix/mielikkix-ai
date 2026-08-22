# CLAUDE.md

Guidance for Claude (and any AI coding assistant) working in this repository.

## Project

**MielikkiX** — a multi-tenant AI chatbot platform for every businesses (retail, service providers, restaurants, clinics, real estate, local shops). Each business gets a branded, embeddable chat widget backed by RAG over their own FAQs/documents, plus an admin dashboard for managing content and leads.

## Tech Stack

| Layer | Choice | Why |
|---|---|---|
| Frontend | React 18 + TypeScript + Vite | Fast dev server, free, huge ecosystem |
| UI | Tailwind CSS + shadcn/ui | Free, no license cost, easy theming per tenant |
| State/data | TanStack Query + Zustand | Lightweight, free |
| Backend | Python 3.12 + FastAPI | Async, typed, free, great for AI/RAG workloads |
| ORM | SQLAlchemy 2.0 + Alembic | Free, mature migrations |
| Database | PostgreSQL | Free, self-hostable |
| Vector store | pgvector extension | Free — avoids paid Pinecone; lives in the same Postgres instance |
| RAG orchestration | LangChain (Python) | Free, open-source |
| Embeddings | `sentence-transformers` (local, free) — fallback to a free-tier hosted embedding API | No per-call cost for MVP |
| LLM | Provider-agnostic layer — Groq (generous free tier, fast), Google Gemini free tier, or local Ollama (Llama 3 / Mistral) — OpenAI/Claude as paid upgrade option | Keeps MVP cost near $0 |
| Auth | JWT via `python-jose` + `passlib` (self-rolled) or Supabase Auth free tier | No license cost |
| File storage | Local disk (MVP) → Supabase Storage free tier or Cloudflare R2 free tier | Free at low volume |
| Background jobs | FastAPI `BackgroundTasks` (MVP) → Celery + Redis (free, self-hosted) later | Keep MVP simple |
| Containerization | Docker + Docker Compose | Free |
| Hosting | Dashboard (`apps/dashboard`) + API (`apps/api`+`db`) on a Hostinger VPS via `docker-compose.yml`, served as two separate hosts (`app.mielikkix.ai` / `api.mielikkix.ai`); marketing site (`website/`) on Hostinger shared hosting, static build | Domain `mielikkix.ai` is already registered/hosted on Hostinger — one vendor for domain, marketing site, and VPS. See `files/ARCHITECTURE.md` §5. |
| CI/CD | GitHub Actions (free for public/small private repos) | Free |
| Monitoring/errors | Sentry free tier | Free |

No paid SaaS is required to build and demo the MVP.

## Repository Structure

Restructured 2026-08-21 into an `apps/` + `packages/` + `infra/` monorepo layout (the flat
`frontend/`/`backend/` layout below is gone — see root `CLAUDE.md` for the full current tree,
including `packages/` and the `apps/agents/` Force agent scaffolds):

```
mielikkix-ai/
├── apps/
│   ├── dashboard/              # React + TypeScript — admin dashboard app + embeddable widget build
│   │   ├── src/
│   │   │   ├── widget/            # Embeddable chat widget (Widget.tsx, ChatWindow, LeadForm; built separately via vite.widget.config.ts)
│   │   │   ├── dashboard/          # Admin dashboard app (pages/, components/) — pages/admin + components/admin hold the separate platform-operator-only /admin area
│   │   │   ├── shared/             # Shared components, hooks, api client
│   │   │   └── main.tsx
│   │   ├── nginx.conf              # prod: serves the build, proxies /api/* to backend
│   │   ├── vite.config.ts
│   │   └── package.json
│   ├── api/                    # FastAPI (was backend/)
│   │   ├── app/
│   │   │   ├── api/                 # Routers: auth, businesses, faqs, documents, products, chat, leads, analytics, websites, admin
│   │   │   ├── core/                 # Config, security, dependencies, plans.py (plan catalog), cors.py, limiter.py
│   │   │   ├── models/                # SQLAlchemy models
│   │   │   ├── schemas/               # Pydantic schemas
│   │   │   ├── services/              # Business logic (auth, chat, document ingestion, plan enforcement)
│   │   │   ├── rag/                    # Embeddings + retrieval pipeline (see files/ARCHITECTURE.md §2.4 for pgvector caveat)
│   │   │   ├── notifications/          # Pluggable notification providers (console / Resend)
│   │   │   └── main.py
│   │   ├── alembic/                 # DB migrations
│   │   ├── tests/
│   │   └── requirements.txt
│   ├── chat-widget/            # README-only for now — widget code still lives in apps/dashboard/src/widget;
│   │                            # no existing seam to cut it out into its own app yet (shares models/db/rag with the API)
│   └── agents/                 # The 10 Mielikkix Force agents — structure-only scaffolds today
├── packages/                   # Shared libs (agent-core, billing, db, auth, ui) — structure-only scaffolds today
├── website/                   # Astro — separate static marketing site (its own stack, own README/ARCHITECTURE.md)
├── infra/                      # docker/ + deploy/ READMEs; docker-compose.yml itself stays at repo root
├── docker-compose.yml
├── files/                      # This doc set
└── .env                        # repo-root .env, read by apps/api/app/core/config.py regardless of cwd
```

## Commands

```bash
# API
cd apps/api
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
alembic upgrade head
uvicorn app.main:app --reload

# Dashboard
cd apps/dashboard
npm install
npm run dev

# Full stack (local)
docker compose up --build

# Tests
cd apps/api && pytest
cd apps/dashboard && npm test
```

## Coding Conventions

- **Multi-tenancy**: every table with business data carries `business_id`; every query MUST filter by the authenticated tenant. Never trust a `business_id` passed from the client without cross-checking the auth token. The one deliberate exception is `apps/api/app/services/admin_service.py` / the `admin` router — platform-operator-only, gated by `require_platform_admin`, intentionally queries across every tenant for the `/admin` dashboard (see `files/ARCHITECTURE.md` §2.7).
- **Backend**: FastAPI routers stay thin; business logic lives in `services/`. Pydantic schemas separate request/response shapes from SQLAlchemy models.
- **Frontend**: the chat widget (`apps/dashboard/src/widget`) must build to a single small bundle with no external runtime dependency on the dashboard — it's embedded via `<script>` on third-party sites.
- **Secrets**: never commit `.env`. All provider keys (LLM, storage) are read from environment variables via `apps/api/app/core/config.py`.
- **RAG**: document ingestion → chunk → embed → store in `document_chunks` (pgvector). Retrieval always scoped by `business_id`.
- **LLM provider abstraction**: all LLM/embedding calls go through `apps/api/app/rag/providers/`, so swapping Groq/Gemini/Ollama/OpenAI/Claude is a config change, not a code change.

## What Claude Should Do

- Prefer the free/open-source option already in the stack table unless the user asks for a paid upgrade.
- When adding a new table, update `files/DATABASE_SCHEMA.md` in the same change.
- When adding a new API route, keep `files/ARCHITECTURE.md`'s endpoint list in sync.
- When a feature actually ships and is verified working, add it to `files/FEATURES.md` — that file's own rule is "real and tested, not aspirational," so don't add something there until it's true.
- Ask before introducing a new paid dependency or service.

## What Claude Should Avoid

- Don't hardcode API keys or write them to files.
- Don't bypass tenant scoping "for convenience" — treat cross-tenant data leaks as a critical bug.
- Don't add Pinecone, paid vector DBs, or paid-only LLM providers as the default path — keep them optional/pluggable.
