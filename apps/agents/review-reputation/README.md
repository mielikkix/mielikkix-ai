# apps/agents/review-reputation

Built and live. Analyzes reviews (sentiment, topics, priority, escalation),
drafts AI reply suggestions in the business's voice, and surfaces reputation
insights/trends — a human always approves a response before it's considered
final; this agent never auto-publishes anywhere.

See [`CLAUDE.md`](./CLAUDE.md) in this directory for integrations needed,
data model, and test criteria — read that before touching this agent's code,
including exactly which real review platforms (Google/Facebook/...) are not
yet connected.
