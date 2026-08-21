"""mielikkix-db

Structure-only scaffold created during the apps/ + packages/ + infra/
restructure. No business logic yet.

Intended contents:
- Shared SQLAlchemy models/schema (currently live in apps/api/app/models/)
  and the multi-tenant data-access layer, so apps/api and the Force agents
  in apps/agents/ don't each re-declare the same tables.
- Every table with business data carries business_id; every query must be
  scoped to the authenticated tenant.
"""

__version__ = "0.0.0"
