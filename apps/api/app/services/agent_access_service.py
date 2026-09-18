"""The one place that answers "is business X entitled to Force agent Y" --
routers call this instead of re-deriving it, same role plan_service plays
for the chat-widget plan. Deliberately separate from plan_service: an
agent's entitlement has nothing to do with the business's chat-widget plan
tier (see apps/api/app/core/agent_catalog.py's module docstring).
"""
from fastapi import HTTPException
from sqlalchemy.orm import Session

from ..core.agent_catalog import AGENTS
from ..models.agent_access import BusinessAgentAccess
from ..models.business import Business


def list_agent_access(db: Session, business_id) -> dict[str, bool]:
    """Every catalog agent key -> whether this business currently has it
    active. Powers GET /api/businesses/me/agents (the dashboard's gate
    source, replacing the old plan.features.*_enabled booleans)."""
    active_keys = {
        row.agent_key
        for row in db.query(BusinessAgentAccess).filter(
            BusinessAgentAccess.business_id == business_id,
            BusinessAgentAccess.status == "active",
        )
    }
    return {key: key in active_keys for key in AGENTS}


def has_agent_access(db: Session, business_id, agent_key: str) -> bool:
    return (
        db.query(BusinessAgentAccess)
        .filter(
            BusinessAgentAccess.business_id == business_id,
            BusinessAgentAccess.agent_key == agent_key,
            BusinessAgentAccess.status == "active",
        )
        .first()
        is not None
    )


def require_agent_access(db: Session, business: Business, agent_key: str) -> None:
    """Same shape as plan_service.require_feature -- raises rather than
    returning a bool, so a router/service can call it as a one-line guard."""
    if not has_agent_access(db, business.id, agent_key):
        agent = AGENTS.get(agent_key)
        name = agent.name if agent else agent_key
        raise HTTPException(
            status_code=403,
            detail=f"{name} isn't active on your account. Purchase it to use this feature.",
        )


def grant_agent_access(db: Session, business_id, agent_key: str) -> BusinessAgentAccess:
    """Admin-only today (no payment processor exists -- see
    apps/api/app/api/admin.py) -- the one place that activates a purchased
    agent. Re-activates a previously revoked row instead of inserting a
    duplicate, since (business_id, agent_key) is unique."""
    if agent_key not in AGENTS:
        raise HTTPException(status_code=400, detail=f"Unknown agent '{agent_key}'.")

    row = (
        db.query(BusinessAgentAccess)
        .filter(BusinessAgentAccess.business_id == business_id, BusinessAgentAccess.agent_key == agent_key)
        .first()
    )
    if row is None:
        row = BusinessAgentAccess(business_id=business_id, agent_key=agent_key, status="active")
        db.add(row)
    else:
        row.status = "active"
    db.commit()
    db.refresh(row)
    return row


def revoke_agent_access(db: Session, business_id, agent_key: str) -> None:
    row = (
        db.query(BusinessAgentAccess)
        .filter(BusinessAgentAccess.business_id == business_id, BusinessAgentAccess.agent_key == agent_key)
        .first()
    )
    if row is not None:
        row.status = "revoked"
        db.commit()
