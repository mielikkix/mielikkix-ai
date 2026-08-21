"""Entrypoint stub for a Mielikkix Force agent.

Copy this whole apps/agents/_template/ folder to apps/agents/<agent-name>/ to
start a new agent, then:
  1. Fill in every <...> in this folder's CLAUDE.md.
  2. Replace this stub with the agent's actual entrypoint, built on
     packages/agent-core (mielikkix_agent_core) for LLM/RAG/tool-calling —
     do not reimplement that plumbing here.
  3. Wire the agent into the shared modular agent process per infra/deploy,
     not as a standalone always-on daemon (see the root CLAUDE.md's
     deployment conventions).

No business logic yet — this is a structure-only scaffold.
"""


def main() -> None:
    raise NotImplementedError(
        "This agent has not been implemented yet. See this folder's "
        "CLAUDE.md for what it should do."
    )


if __name__ == "__main__":
    main()
