"""mielikkix-auth

Structure-only scaffold created during the apps/ + packages/ + infra/
restructure. No business logic yet.

Intended contents:
- Shared session/JWT auth logic (currently lives in
  apps/api/app/core/security.py and apps/api/app/api/auth.py), so any new
  agent process can authenticate/authorize tenant requests the same way
  apps/api does, without reimplementing it.
"""

__version__ = "0.0.0"
