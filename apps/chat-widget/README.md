# apps/chat-widget — placeholder

This directory is a **placeholder**, not yet a working app. It exists so the
target `apps/` layout is visible in the repo, but no code has been moved here.

## Why the widget isn't split out yet

The target structure calls for `apps/chat-widget/` (the live embeddable widget:
RAG Q&A, lead capture) to be separate from `apps/api/` (core backend: auth,
tenant/business management, dashboard-facing routes, orchestration).

Looking at the actual code during the `apps/` + `packages/` + `infra/`
restructure (2026-08-21), the backend (`backend/`, now `apps/api/`) is a single
FastAPI app where widget-serving concerns and general platform concerns are
tightly interwoven, not cleanly separable:

- `apps/api/app/api/chat.py` (the widget's chat endpoint) shares
  `app/core/database.py`, `app/models/*`, `app/core/security.py`,
  `app/core/plans.py`, and `app/rag/*` with the dashboard/admin routers
  (`businesses.py`, `documents.py`, `faqs.py`, `products.py`, `leads.py`,
  `analytics.py`, `admin.py`, `auth.py`).
- There's one `main.py`, one set of SQLAlchemy models, one Alembic migration
  history, and one `requirements.txt` for the whole thing — no existing
  module boundary marks "widget engine" vs. "platform logic."

Forcing a code split here blind — while this is a **live production service**
— risked breaking the Chat Widget or the dashboard for the sake of a directory
layout. So for this pass, the entire backend was moved as-is to `apps/api/`
(preserving git history via `git mv`), and this folder was added only as a
placeholder for a **future, deliberate** extraction once the widget-specific
surface (likely just `app/api/chat.py` + the parts of `app/rag/` it needs) can
be carved out carefully, with tests, rather than guessed at during a file move.

See the restructure summary in the PR/commit description for the full
reasoning. Until that extraction happens, the live Chat Widget's backend code
lives in `apps/api/` alongside everything else.
