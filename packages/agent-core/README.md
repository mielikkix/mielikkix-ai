# packages/agent-core

The shared runtime every Mielikkix Force agent is built on. It generalizes the
engine already powering the live Chat Widget — the same RAG/LLM plumbing,
extended so any agent can use it, not just the widget.

This is currently a **structure-only scaffold** (added during the apps/ +
packages/ + infra/ restructure) — no business logic has been moved or written
here yet.

See [`CLAUDE.md`](./CLAUDE.md) in this directory for the full spec: what
belongs here, what doesn't, and testing expectations.
