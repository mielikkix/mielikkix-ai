"""mielikkix-agent-core

Structure-only scaffold created during the apps/ + packages/ + infra/
restructure. No business logic yet.

Intended contents (see this package's CLAUDE.md for the full spec):
- LLM client: a single wrapper around whichever provider SDK(s) are called,
  with retries, timeouts, and cost/usage logging built in once, centrally.
- Prompt / tool-calling framework: the pattern every agent uses to define its
  tools/functions and get structured output back.
- Memory / RAG utilities: document/FAQ/catalog retrieval, embeddings, and
  context assembly, shared by the Chat Widget and every Force agent.
- Tenant context loader: given a request, resolve which business it's for and
  which agents that tenant is entitled to (via mielikkix_billing).
"""

__version__ = "0.0.0"
