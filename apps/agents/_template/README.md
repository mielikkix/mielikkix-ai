# apps/agents/_template

Template for a Mielikkix Force agent. **Copy this whole folder** to
`apps/agents/<agent-name>/` to start a new agent, then fill in every `<...>`
in [`CLAUDE.md`](./CLAUDE.md) before writing code. The 6 queued agents (see
that file's reference table) already have their own scaffolded folder built
from this template — this is only needed again for a brand-new agent added
to the roster.

This is a structure-only scaffold: `pyproject.toml` + `app/main.py` give a
minimal buildable stub, built on `packages/agent-core` once that package has
real logic in it.
