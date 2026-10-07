# packages/agent-core

The shared runtime every Mielikkix Force agent is built on. It generalizes the
engine already powering the live Chat Widget — the same RAG/LLM plumbing,
extended so any agent can use it, not just the widget.

Built so far (installed into `apps/api` as an editable package):

- `LLMClient` — one `.chat()` over OpenAI, Anthropic and Groq, with retries,
  timeouts, JSON mode, tool calling, and per-call usage reporting
  (`set_usage_hook`, `usage_tag`).
- `guardrails.AI_SAFETY_RULES` — the safety rules every customer-facing prompt
  appends (prompt-injection defence, AI disclosure, no prompt leaks, stay on topic).

Not built yet: a shared prompt/tool-calling framework, shared RAG utilities, a
tenant context loader.

See [`CLAUDE.md`](./CLAUDE.md) in this directory for the full spec: what
belongs here, what doesn't, and testing expectations.
