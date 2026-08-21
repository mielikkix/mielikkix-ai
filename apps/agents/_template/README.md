# apps/agents/_template

Template for a Mielikkix Force agent. **Copy this whole folder** to
`apps/agents/<agent-name>/` to start any of the remaining 7 agents, then fill
in every `<...>` in [`CLAUDE.md`](./CLAUDE.md) before writing code.

This is a structure-only scaffold: `pyproject.toml` + `app/main.py` give a
minimal buildable stub, built on `packages/agent-core` once that package has
real logic in it.
