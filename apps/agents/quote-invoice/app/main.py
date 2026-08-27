"""Entrypoint stub for the Quote & Invoice agent.

See this folder's CLAUDE.md for the full spec (request parsing into
itemized quote lines, PDF generation, deferred Stripe payment collection).
No business logic yet -- this is a structure-only scaffold built on top of
packages/agent-core (mielikkix_agent_core) once that package is real.
"""


def main() -> None:
    raise NotImplementedError(
        "Quote & Invoice agent is not implemented yet. See CLAUDE.md in "
        "this folder for the spec."
    )


if __name__ == "__main__":
    main()
