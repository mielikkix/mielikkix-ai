# packages/db

Shared schema/models and the multi-tenant data layer. Every table with
business data carries `business_id`; every query must be scoped to the
authenticated tenant — see the root `CLAUDE.md` for the multi-tenancy rule.

This is currently a **structure-only scaffold** (added during the apps/ +
packages/ + infra/ restructure). The actual SQLAlchemy models and Alembic
migration history still live in `apps/api/app/models/` and
`apps/api/alembic/` — nothing has been moved out of there yet. Extracting
them into this package is a future, deliberate step (not done blind during
the file move, since the live Chat Widget and dashboard depend on that data
layer working correctly).
