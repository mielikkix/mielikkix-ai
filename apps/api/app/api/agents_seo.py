"""SEO Copywriter -- HTTP wrapper. See apps/agents/seo-copywriter/CLAUDE.md
for the full spec and app/services/seo_service.py for the actual logic --
this file only maps HTTP <-> that service, the same split app/api/
agents_booking.py uses for app/services/booking_service.py.
"""

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from ..core.database import get_db
from ..core.dependencies import get_current_user, get_current_business
from ..models.business import Business
from ..models.user import User
from ..services import plan_service, seo_service

router = APIRouter(prefix="/api/agents/seo", tags=["seo-copywriter"])


class _DraftOut(BaseModel):
    id: str
    product_id: str
    draft_description: str
    draft_seo_title: str
    draft_meta_description: str
    status: str

    @classmethod
    def from_orm_draft(cls, draft) -> "_DraftOut":
        return cls(
            id=str(draft.id),
            product_id=str(draft.product_id),
            draft_description=draft.draft_description,
            draft_seo_title=draft.draft_seo_title,
            draft_meta_description=draft.draft_meta_description,
            status=draft.status,
        )


class _GenerateRequest(BaseModel):
    product_ids: list[str]


@router.post("/drafts/generate", response_model=list[_DraftOut])
async def generate_drafts(
    body: _GenerateRequest,
    current_user: User = Depends(get_current_user),
    business: Business = Depends(get_current_business),
    db: Session = Depends(get_db),
):
    plan_service.require_feature(business, "seo_copywriter_enabled")
    drafts = await seo_service.generate_drafts(db, str(current_user.business_id), body.product_ids)
    return [_DraftOut.from_orm_draft(d) for d in drafts]


@router.get("/drafts", response_model=list[_DraftOut])
def list_drafts(
    status: str | None = None,
    current_user: User = Depends(get_current_user),
    business: Business = Depends(get_current_business),
    db: Session = Depends(get_db),
):
    plan_service.require_feature(business, "seo_copywriter_enabled")
    drafts = seo_service.list_drafts(db, str(current_user.business_id), status)
    return [_DraftOut.from_orm_draft(d) for d in drafts]


@router.post("/drafts/{draft_id}/approve", response_model=_DraftOut)
def approve_draft(
    draft_id: str,
    current_user: User = Depends(get_current_user),
    business: Business = Depends(get_current_business),
    db: Session = Depends(get_db),
):
    plan_service.require_feature(business, "seo_copywriter_enabled")
    draft = seo_service.approve_draft(db, str(current_user.business_id), draft_id)
    if draft is None:
        raise HTTPException(status_code=404, detail="Draft not found")
    return _DraftOut.from_orm_draft(draft)


@router.post("/drafts/{draft_id}/reject", response_model=_DraftOut)
def reject_draft(
    draft_id: str,
    current_user: User = Depends(get_current_user),
    business: Business = Depends(get_current_business),
    db: Session = Depends(get_db),
):
    plan_service.require_feature(business, "seo_copywriter_enabled")
    draft = seo_service.reject_draft(db, str(current_user.business_id), draft_id)
    if draft is None:
        raise HTTPException(status_code=404, detail="Draft not found")
    return _DraftOut.from_orm_draft(draft)
