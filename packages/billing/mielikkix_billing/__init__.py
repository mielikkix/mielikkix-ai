"""mielikkix-billing

Structure-only scaffold created during the apps/ + packages/ + infra/
restructure. No business logic yet.

Intended contents:
- Subscription/plan catalog (individual agent, 3-agent bundle, Full Crew).
- The single entitlement check used by both apps/api routes and
  apps/dashboard module rendering — no second, hand-rolled gate anywhere else.
- Adding a new agent to a tenant's plan is a change here, not a deployment
  change.
"""

__version__ = "0.0.0"
