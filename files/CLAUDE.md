# CLAUDE.md

Guidance for Claude (and any AI coding assistant) working in this repository.

## Project

**Mielikkix** — a multi-tenant AI platform for small businesses (retail, service providers, restaurants, clinics, real estate, local shops). Each business gets a branded, embeddable chat widget backed by RAG over their own FAQs/documents/products, an admin dashboard (English/Norwegian) for content, leads and conversations, and optional Mielikkix Force AI agents (Voice Receptionist, Booking Assistant, Support Triage, Review & Reputation, SEO Audit & Optimize, Email Marketing).

## Tech Stack

As actually installed (`apps/api/requirements.txt`, `apps/dashboard/package.json`,
`website/package.json`, `docker-compose.yml`) — last checked 2026-10-07.

| Layer | Choice | Notes |
|---|---|---|
| Backend | Python 3.12 + FastAPI 0.111 on Uvicorn | Async, typed; one app (`apps/api`) serves the widget, dashboard, admin and every Force agent route |
| Validation/config | Pydantic v2 + pydantic-settings, python-dotenv | One root `.env` |
| ORM / migrations | SQLAlchemy 2.0 + Alembic | psycopg2 driver |
| Database | PostgreSQL 16 + pgvector extension (`pgvector/pgvector:pg16` image) | Embeddings are currently stored as JSON text and scored in Python — see `files/ARCHITECTURE.md` §2.4 |
| RAG | Hand-rolled pipeline (`apps/api/app/rag/pipeline.py`, chunking in `services/document_service.py`) + `sentence-transformers` (`paraphrase-multilingual-MiniLM-L12-v2`, local, CPU-only torch) | No paid vector DB. `langchain` is still in `requirements.txt` but nothing imports it |
| Chat Widget LLM | Per-business provider abstraction (`apps/api/app/rag/providers/`): Groq (default, `openai/gpt-oss-120b`), Google Gemini, Ollama | See `files/LLM_MODELS.md` |
| Force agent LLM | `packages/agent-core` `LLMClient`: OpenAI (`gpt-4o` / `gpt-4o-mini`), Anthropic Claude Sonnet (Opus reserved), Groq | Shared AI safety rules in `agent-core/guardrails.py`; usage hook logs every call |
| Auth | Self-rolled JWT (`python-jose`) in an httpOnly cookie, `passlib`/bcrypt passwords | `PLATFORM_ADMIN_EMAILS` allowlist for `/admin` |
| Security | `cryptography` (Fernet — OAuth tokens encrypted at rest), `slowapi` rate limiting, `bleach` HTML sanitizing, SSRF guards, Twilio signature validation | |
| Document parsing / crawling | PyPDF2, python-docx, openpyxl, BeautifulSoup4, httpx/requests | Website crawler shared by knowledge-base import and SEO audits |
| Integrations | Twilio (voice), Google Calendar, Google Business Profile (reviews), Google Analytics Data + Search Console + PageSpeed Insights, Mailchimp (OAuth + Marketing API), Resend (email) | Each behind a provider abstraction (root `CLAUDE.md` convention #6) |
| Scheduling | APScheduler (in-process; SEO recurring audits) + FastAPI `BackgroundTasks` | No Celery/Redis job queue yet |
| Website deploy | paramiko (SFTP upload of `website/dist/` to Hostinger from the admin Articles publish flow) | |
| Dashboard + widget | React 18 + TypeScript 5 + Vite 5 | Widget built separately (`vite.widget.config.ts`) into one `widget.js`, Shadow DOM |
| UI | Tailwind CSS 3 (PostCSS/Autoprefixer), lucide-react icons, clsx | Hand-built components in `apps/dashboard/src/shared/components` (no shadcn/ui) |
| State/data | TanStack Query 5 + Zustand, axios, React Router 6 | |
| i18n | Own lightweight i18n (`apps/dashboard/src/shared/i18n`) — English + Norwegian Bokmål | User's choice stored on `users.locale` |
| Marketing site | Astro 7 (static) + Tailwind CSS 4, TypeScript, `@astrojs/sitemap`, self-hosted Open Sans (Fontsource), custom `/no/` page-generation integration | See `website/ARCHITECTURE.md` |
| Tests | pytest + pytest-asyncio (API), Vitest (dashboard), `node --test` (website) | |
| Containers | Docker + Docker Compose (`db`, `backend`, `frontend`); dashboard served by nginx | |
| Hosting | Dashboard (`app.mielikkix.ai`) + API (`api.mielikkix.ai`) + Postgres on a Hostinger VPS via `docker-compose.yml`; marketing site on Hostinger shared hosting (static) | See `files/ARCHITECTURE.md` §5 |
| CI | GitHub Actions (`.github/workflows/ci.yml`): API tests, migration check, dashboard + widget builds | Website build/tests and deploys are not in CI |

Not used (despite earlier plans): LangChain (installed, unused), shadcn/ui, Supabase, Sentry, Celery/Redis, Cal.com.

## Repository Structure

`apps/` + `packages/` + `infra/` monorepo (restructured 2026-08-21; see root `CLAUDE.md` for the
full tree). Note that **all Force agent code actually lives in `apps/api`** (routers
`app/api/agents_*.py`, services `app/services/*`); the `apps/agents/<name>/` folders hold each
agent's spec (`CLAUDE.md`) plus a stub `app/main.py`.

```
mielikkix-ai/
├── apps/
│   ├── dashboard/              # React + TypeScript — business dashboard, /admin area, and the embeddable widget build
│   │   ├── src/
│   │   │   ├── widget/            # Chat widget (Widget, ChatWindow, LeadForm, BookingFlow, ConsentGate; vite.widget.config.ts)
│   │   │   ├── dashboard/         # pages/ (incl. settings/, admin/) + components/
│   │   │   ├── shared/            # api client, components, hooks, i18n (en + nb), auth store
│   │   │   └── main.tsx
│   │   ├── nginx.conf             # prod: serves the SPA build
│   │   └── package.json
│   ├── api/                    # FastAPI
│   │   ├── app/
│   │   │   ├── api/               # Routers: auth, account, consent, businesses, websites, faqs, documents, products,
│   │   │   │                      #   chat, leads, analytics, admin, admin_articles, public_articles,
│   │   │   │                      #   agents_{voice,booking,support,reviews,seo,seo_audit}, campaigns,
│   │   │   │                      #   {calendar,review,google,mailchimp}_oauth
│   │   │   ├── core/              # config, security, dependencies, plans.py, agent_catalog.py, encryption, legal, locale, limiter, cors
│   │   │   ├── models/            # SQLAlchemy models (see files/DATABASE_SCHEMA.md)
│   │   │   ├── schemas/           # Pydantic schemas
│   │   │   ├── services/          # Business logic (chat, documents, plans, agent access, booking, support, reviews,
│   │   │   │                      #   seo_*, campaigns, retention, account, articles, deploy, ...)
│   │   │   ├── integrations/      # Provider abstractions: calendar, review platforms, email marketing, Google, Mailchimp, PageSpeed
│   │   │   ├── rag/               # Embeddings, language detection, retrieval pipeline, LLM providers
│   │   │   ├── notifications/     # console / Resend providers + email templates (en/nb)
│   │   │   └── main.py
│   │   ├── alembic/               # DB migrations
│   │   ├── scripts/
│   │   ├── tests/
│   │   └── requirements.txt
│   ├── chat-widget/            # README-only placeholder — widget code lives in apps/dashboard/src/widget
│   └── agents/                 # One folder per Force agent: spec (CLAUDE.md) + stub; code is in apps/api
├── packages/
│   ├── agent-core/             # REAL: LLMClient (OpenAI/Anthropic/Groq), guardrails, usage hook
│   └── billing/ db/ auth/ ui/  # structure-only scaffolds — the logic still lives in apps/api
├── website/                    # Astro marketing site (own README/ARCHITECTURE.md)
├── docs/                       # BRAND.md, pricing-rules.md, privacy/ (GDPR records)
├── infra/                      # docker/ + deploy/ READMEs; docker-compose.yml stays at repo root
├── .github/workflows/ci.yml
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

# Marketing site
cd website
npm install
npm run dev

# Tests
cd apps/api && pytest
cd apps/dashboard && npm test
cd website && npm test
```

## Coding Conventions

- **Multi-tenancy**: every table with business data carries `business_id`; every query MUST filter by the authenticated tenant. Never trust a `business_id` passed from the client without cross-checking the auth token. The one deliberate exception is `apps/api/app/services/admin_service.py` / the `admin` router — platform-operator-only, gated by `require_platform_admin`, intentionally queries across every tenant for the `/admin` dashboard (see `files/ARCHITECTURE.md` §2.7).
- **Backend**: FastAPI routers stay thin; business logic lives in `services/`. Pydantic schemas separate request/response shapes from SQLAlchemy models.
- **Frontend**: the chat widget (`apps/dashboard/src/widget`) must build to a single small bundle with no external runtime dependency on the dashboard — it's embedded via `<script>` on third-party sites.
- **Secrets**: never commit `.env`. All provider keys (LLM, storage) are read from environment variables via `apps/api/app/core/config.py`.
- **RAG**: document ingestion → chunk → embed → store in `document_chunks.embedding_json` (FAQs and products carry their own `embedding_json` too). Retrieval always scoped by `business_id`.
- **LLM provider abstraction**: the Chat Widget's LLM calls go through `apps/api/app/rag/providers/` (Groq/Gemini/Ollama, per business); every Force agent goes through `packages/agent-core`'s `LLMClient` (OpenAI/Anthropic/Groq). Never call a provider SDK directly. See `files/LLM_MODELS.md`.
- **Agent access**: every agent route/module checks `agent_access_service.require_agent_access` (`business_agent_access` table) — don't add a second gate.

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
