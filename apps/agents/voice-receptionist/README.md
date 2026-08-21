# apps/agents/voice-receptionist

Flagship Force agent (build order: Day 4). Answers inbound calls, holds a
natural voice conversation grounded in the business's info via
`packages/agent-core`'s RAG layer, books appointments or takes a message, and
notifies the business owner.

See [`CLAUDE.md`](./CLAUDE.md) in this directory for integrations needed,
data model, and test criteria — read that before touching this agent's code.

This is currently a **structure-only scaffold** — no business logic yet.
