# CLAUDE.md — packages/agent-core

Place this file at `mielikkix-ai/packages/agent-core/CLAUDE.md`.

## What this package is

The shared runtime every Mielikkix Force agent is built on. It generalizes the engine
already powering the live Chat Widget — the same RAG/LLM plumbing, extended so any
agent can use it, not just the widget.

## Current status (honesty check for whoever reads this next)

Only the **LLM client** below is actually built (`mielikkix_agent_core.LLMClient`,
`LLMResult`, `LLMUsage` — a thin wrapper with retries/JSON-mode, no tool-calling). The
**prompt/tool-calling framework**, **memory/RAG utilities**, and **tenant context
loader** below are still just this file's stated intent, not code that exists yet.
Concretely: the Chat Widget (`rag/pipeline.py`), Support Triage, Voice Receptionist,
and Booking Assistant each hand-roll their own system prompt and their own JSON output
shape against the shared `LLMClient` — there is no shared classification/dispatch
layer. The chat-widget → Booking Assistant handoff (`chat_service.py`'s
`suggest_booking_flow`, see `apps/agents/booking-assistant/CLAUDE.md`) is a real
example of what a generalized tool-router would eventually replace: it's a single
boolean flag set by a keyword classifier, not an agent-core capability, and it should
be read as evidence for *why* this framework is worth building, not as it having been
built. Don't assume anything else in this file exists without checking the actual
code first.

## What belongs here

- **LLM client** — a single wrapper around whichever provider SDK(s) you call
  (OpenAI / Anthropic / etc.), with retries, timeouts, and cost/usage logging built in
  once, centrally.
- **Prompt / tool-calling framework** — the pattern every agent uses to define its
  available tools/functions and get structured output back. One convention, reused
  10 times.
- **Memory / RAG utilities** — document/FAQ/catalog retrieval, embeddings, and context
  assembly, shared by the widget and every agent.
- **Tenant context loader** — given a request, resolve which business it's for, which
  documents/config apply, and which agents that tenant is entitled to (calls
  `packages/billing` for the entitlement check — agent-core does not duplicate that logic).

## What does NOT belong here

- Anything specific to one agent's business logic (e.g. call-handling flow logic belongs
  in `apps/agents/voice-receptionist/`, not here).
- Billing/subscription logic (`packages/billing`).
- UI components (`packages/ui`).

## Conventions for adding a new capability

1. If two or more agents need the same capability, it goes in agent-core — not copy-pasted.
2. Every function here must work for any tenant/agent combination; nothing tenant-specific
   or agent-specific is hardcoded.
3. Breaking changes here affect every agent and the widget — bump a version marker in
   this file's changelog section (add one) and note which agents were tested against it.

## Testing expectations

- Unit tests for the LLM client (mock provider responses; test retry/timeout behavior).
- Unit tests for RAG retrieval (given a known document set, verify expected chunks return).
- Any agent PR that touches agent-core must also state which agents were regression-tested.
