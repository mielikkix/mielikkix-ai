# apps/agents/support-triage

Flagship Force agent. Powers the chat widget live sitewide on `website/`
(`public/support-chat-widget.js`, embedded via `Layout.astro`), classifies
incoming messages, answers what it confidently can via `packages/agent-core`'s
RAG layer, drafts replies for the rest, and escalates to a human by email when
it should.

See [`CLAUDE.md`](./CLAUDE.md) in this directory for integrations needed,
data model, and test criteria — read that before touching this agent's code.

Core flow is built and live. See CLAUDE.md's Definition of Done for exact
status on the Voice Receptionist handoff and VPS deploy.
