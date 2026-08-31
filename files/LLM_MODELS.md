# MielikkiX — Which LLM Model Powers Which Feature

A reference for exactly which provider/model each feature actually calls, why,
and how to change it. Two separate systems exist — don't confuse them:

1. **The Chat Widget's own provider system** — per-tenant, swappable
   (Groq / Gemini / Ollama), unrelated to the tier assignment below.
2. **The Force agents' tier assignment** — five agents, each hardcoded (at
   construction time, in code) to a specific provider/tier via
   `packages/agent-core`'s `LLMClient`.

---

## 1. Chat Widget (the live product)

The embeddable, customer-facing chat widget every tenant business uses is
**not** part of the tier system below — it has its own, older, per-tenant
provider abstraction (`apps/api/app/rag/providers/`), predating the
multi-provider `LLMClient`.

| Setting | Where it lives | Default |
|---|---|---|
| Provider | `BusinessSettings.llm_provider` (per business), falls back to `settings.default_llm_provider` | `groq` |
| Model | `BusinessSettings.llm_model` (per business), falls back to `settings.groq_model` / `gemini_model` / `ollama_model` | `openai/gpt-oss-120b` (Groq) |

A business can switch itself to Gemini or a self-hosted Ollama model from
their own settings — see `rag/providers/__init__.py`'s `get_llm_provider()`.
**Every existing tenant is on Groq by default** — do not remove
`GROQ_API_KEY`/`GROQ_MODEL` from `.env`, that breaks live customer traffic
(confirmed explicitly with the user 2026-08-30 — Groq stays).

## 2. The Force agents — tier assignment

Added when Groq's own rate-limiting started stalling live voice calls for a
minute-plus (see `packages/agent-core/mielikkix_agent_core/llm_client.py`'s
own comments). Each agent's `_llm_client` is constructed with an explicit
`provider=`, independent of `DEFAULT_LLM_PROVIDER`:

| Feature | File | Provider | Model | Env var(s) |
|---|---|---|---|---|
| **Voice Receptionist** | `apps/api/app/api/agents_voice.py` | OpenAI | `gpt-4o` | `OPENAI_API_KEY`, `OPENAI_MODEL` |
| **Booking Agent** (parses "next Tuesday afternoon" into real dates — shared by Voice *and* the standalone Booking Assistant chat/demo) | `apps/api/app/services/booking_service.py` | Anthropic | `claude-sonnet-5` | `ANTHROPIC_API_KEY`, `ANTHROPIC_MODEL` |
| **Support Triage** (classification + drafted answer + escalation) | `apps/api/app/services/support_service.py` | Anthropic | `claude-sonnet-5` | `ANTHROPIC_API_KEY`, `ANTHROPIC_MODEL` |
| **SEO Copywriter** (product description/metadata drafts) | `apps/api/app/services/seo_service.py` | OpenAI | `gpt-4o-mini` | `OPENAI_API_KEY`, `OPENAI_MINI_MODEL` |
| **Review & Reputation** (sentiment/priority analysis, response drafting, reputation summary) | `apps/api/app/services/review_service.py` | OpenAI | `gpt-4o-mini` | `OPENAI_API_KEY`, `OPENAI_MINI_MODEL` |

**Reserved, not assigned to anything today**: `ANTHROPIC_OPUS_MODEL`
(`claude-opus-5`) — available for a future workflow that genuinely needs
deeper reasoning than Sonnet. Don't reach for it without a real need.

### Why this split

- **OpenAI (`gpt-4o` / `gpt-4o-mini`)** — low-latency and/or cheap, routine
  work: Voice needs fast turn-taking for a live conversation; SEO/Review are
  single-call, structured-output tasks with no multi-step reasoning.
- **Anthropic Claude Sonnet** — multi-turn reasoning and structured tool
  use: Booking's date-parsing has to handle genuinely ambiguous phrasing
  ("sometime next week, afternoons work best"); Support Triage does
  classification + confidence-gated answering + a booking-intent handoff
  in one call.
- **Groq stays the *default*** (`DEFAULT_LLM_PROVIDER=groq` in `.env`) for
  anything that doesn't specify a provider — but every agent above now
  specifies one explicitly, so this default currently only matters for the
  Chat Widget (see section 1) and any future agent that doesn't opt into a
  tier.

## 3. How to change a model

Each is a plain env var — no code change needed to swap models within the
same provider (e.g. a future `gpt-5` release):

```
OPENAI_MODEL=gpt-4o              # Voice Receptionist
OPENAI_MINI_MODEL=gpt-4o-mini    # SEO Copywriter, Review & Reputation
ANTHROPIC_MODEL=claude-sonnet-5  # Booking Agent, Support Triage
ANTHROPIC_OPUS_MODEL=claude-opus-5   # reserved, unused
GROQ_MODEL=openai/gpt-oss-120b   # Chat Widget default
```

Switching an agent to a *different provider* (not just a different model on
the same provider) means changing that one line in the agent's own service
file, e.g. `booking_service.py`:

```python
_llm_client = LLMClient(provider="anthropic")
```

See `packages/agent-core/mielikkix_agent_core/llm_client.py` for the full
provider abstraction (Groq/OpenAI/Anthropic behind one shared `.chat()`
contract) and `apps/agents/CLAUDE.md` for the tier-assignment convention
this table documents.
