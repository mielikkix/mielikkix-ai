# apps/agents/support-triage

Flagship Force agent (build order: Day 4-ish, alongside the other two).
Powers the chat widget on `website/` (the marketing site currently has no
live widget, only a static mockup), classifies incoming messages, answers
what it confidently can via `packages/agent-core`'s RAG layer, drafts
replies for the rest, and escalates to a human by email when it should.

See [`CLAUDE.md`](./CLAUDE.md) in this directory for integrations needed,
data model, and test criteria — read that before touching this agent's code.

This is currently a **structure-only scaffold** — no business logic yet.
