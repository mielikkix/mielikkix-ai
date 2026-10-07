# packages/billing

Entitlement + subscription logic (individual agent / 3-agent bundle / Full
Crew). This is the **single source of truth** for what a tenant is entitled
to — both `apps/api` routes and `apps/dashboard` module rendering must call
the same check here, never a second hand-rolled gate.

This is currently a **structure-only scaffold** — no logic has been moved
here yet. Today the real checks live in `apps/api`:

- Chat Widget plans/limits: `app/core/plans.py` + `app/services/plan_service.py`
- Force agent access: `app/core/agent_catalog.py` (catalog/prices) +
  `app/services/agent_access_service.py` (`business_agent_access` table) —
  the one check every agent route and dashboard module uses.

There is no payment processor; paid plans are set by a platform admin.
