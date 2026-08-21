# packages/billing

Entitlement + subscription logic (individual agent / 3-agent bundle / Full
Crew). This is the **single source of truth** for what a tenant is entitled
to — both `apps/api` routes and `apps/dashboard` module rendering must call
the same check here, never a second hand-rolled gate.

This is currently a **structure-only scaffold** (added during the apps/ +
packages/ + infra/ restructure) — no business logic has been moved or written
here yet.
