# apps/agents/support-triage

Flagship Force agent. Powers the live demo at `/demo/support-triage` on
`website/` (`public/support-triage.js`), classifies
incoming messages, answers what it confidently can via `packages/agent-core`'s
RAG layer, drafts replies for the rest, and escalates to a human by email when
it should.

See [`CLAUDE.md`](./CLAUDE.md) in this directory for integrations needed,
data model, and test criteria — read that before touching this agent's code.

Built and live: classification (Claude Sonnet), confidence-gated answers,
email escalation, booking handoff, Voice Receptionist ticket handoff, and the
operator's ticket inbox at `/admin/tickets`. Code lives in `apps/api`
(`app/api/agents_support.py`, `app/services/support_service.py`). Serves
Mielikkix's own visitors only — not sold per tenant yet.
