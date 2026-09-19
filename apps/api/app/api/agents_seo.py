"""SEO Copywriter -- HTTP wrapper. See apps/agents/seo-copywriter/CLAUDE.md
for the full spec and app/services/seo_service.py for the actual logic --
this file only maps HTTP <-> that service, the same split app/api/
agents_booking.py uses for app/services/booking_service.py.

Stage 7 added a second draft-generation entry point (one piece of copy
targeted at a specific SEO Audit finding, see agents_seo_audit.py's
findings_router) alongside the original product-picker flow below -- both
routers share the one SeoDraftOut schema (schemas/seo_draft.py) so a draft
looks the same regardless of which flow created it.
"""

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from ..core.database import get_db
from ..core.dependencies import get_current_user, get_current_business
from ..models.business import Business
from ..models.user import User
from ..schemas.seo_draft import SeoDraftOut
from ..services import agent_access_service, seo_service

router = APIRouter(prefix="/api/agents/seo", tags=["seo-copywriter"])


class _GenerateRequest(BaseModel):
    product_ids: list[str]


@router.post("/drafts/generate", response_model=list[SeoDraftOut])
async def generate_drafts(
    body: _GenerateRequest,
    current_user: User = Depends(get_current_user),
    business: Business = Depends(get_current_business),
    db: Session = Depends(get_db),
):
    agent_access_service.require_agent_access(db, business, "seo_audit_optimization")
    drafts = await seo_service.generate_drafts(db, str(current_user.business_id), body.product_ids)
    return [SeoDraftOut.from_orm_draft(d) for d in drafts]


@router.get("/drafts", response_model=list[SeoDraftOut])
def list_drafts(
    status: str | None = None,
    current_user: User = Depends(get_current_user),
    business: Business = Depends(get_current_business),
    db: Session = Depends(get_db),
):
    agent_access_service.require_agent_access(db, business, "seo_audit_optimization")
    drafts = seo_service.list_drafts(db, str(current_user.business_id), status)
    return [SeoDraftOut.from_orm_draft(d) for d in drafts]


@router.post("/drafts/{draft_id}/approve", response_model=SeoDraftOut)
def approve_draft(
    draft_id: str,
    current_user: User = Depends(get_current_user),
    business: Business = Depends(get_current_business),
    db: Session = Depends(get_db),
):
    agent_access_service.require_agent_access(db, business, "seo_audit_optimization")
    draft = seo_service.approve_draft(db, str(current_user.business_id), draft_id)
    if draft is None:
        raise HTTPException(status_code=404, detail="Draft not found")
    return SeoDraftOut.from_orm_draft(draft)


@router.post("/drafts/{draft_id}/reject", response_model=SeoDraftOut)
def reject_draft(
    draft_id: str,
    current_user: User = Depends(get_current_user),
    business: Business = Depends(get_current_business),
    db: Session = Depends(get_db),
):
    agent_access_service.require_agent_access(db, business, "seo_audit_optimization")
    draft = seo_service.reject_draft(db, str(current_user.business_id), draft_id)
    if draft is None:
        raise HTTPException(status_code=404, detail="Draft not found")
    return SeoDraftOut.from_orm_draft(draft)
