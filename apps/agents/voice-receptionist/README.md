# apps/agents/voice-receptionist

Flagship Force agent (build order: Day 4). Answers inbound calls, holds a
natural voice conversation grounded in the business's info via
`packages/agent-core`'s RAG layer, books appointments or takes a message, and
notifies the business owner.

See [`CLAUDE.md`](./CLAUDE.md) in this directory for integrations needed,
data model, and test criteria — read that before touching this agent's code.

Core flow is built and tested: inbound-call handling, RAG-grounded conversation,
and a deterministic propose/finalize booking flow with a natural readback
confirmation. See [`CLAUDE.md`](./CLAUDE.md)'s Definition of Done for exact status
on the Support Triage handoff, call-summary notifications, and VPS deploy.
