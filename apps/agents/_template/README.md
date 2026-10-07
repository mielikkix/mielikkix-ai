# apps/agents/_template

Template for a Mielikkix Force agent. **Copy this whole folder** to
`apps/agents/<agent-name>/` to start a new agent, then fill in every `<...>`
in [`CLAUDE.md`](./CLAUDE.md) before writing code. Every agent on the roster
already has its own folder (see that file's reference table; 4 are still
queued) — this is only needed again for a brand-new agent.

Note: the built agents' running code lives in `apps/api` (routers in
`app/api/agents_*.py`, logic in `app/services/`), not in their own folders —
follow that pattern rather than standing up a separate app.

This is a structure-only scaffold: `pyproject.toml` + `app/main.py` give a
minimal buildable stub, built on `packages/agent-core` once that package has
real logic in it.
