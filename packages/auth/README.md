# packages/auth

Shared session/auth logic, for use across `apps/api` and any Force agent
process that needs to authenticate or authorize a tenant request the same
way.

This is currently a **structure-only scaffold** (added during the apps/ +
packages/ + infra/ restructure). The actual auth logic still lives in
`apps/api/app/core/security.py` and `apps/api/app/api/auth.py` — nothing has
been moved out of there yet, to avoid touching live auth code blind during
the file move.
