"""Unused entrypoint stub for the SEO Audit & Optimization agent.

The real implementation lives in apps/api (app/services/seo_*.py,
app/api/agents_seo*.py) per the root CLAUDE.md's "modular process, not one
container per agent" convention -- this folder's own app/ package was never
actually wired up as a running service. See this folder's CLAUDE.md for the
full spec and current build status.
"""


def main() -> None:
    raise NotImplementedError(
        "This folder is a docs-only scaffold. The SEO Audit & Optimization "
        "agent itself is built and live in apps/api -- see CLAUDE.md in "
        "this folder for where."
    )


if __name__ == "__main__":
    main()
