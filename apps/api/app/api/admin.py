from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from ..core.database import get_db
from ..core.dependencies import require_platform_admin
from ..schemas.admin import (
    AdminBusinessListOut,
    AdminBusinessDetailOut,
    AdminBusinessStatusUpdate,
    AdminBusinessPlanUpdate,
    AdminOverviewOut,
    AdminLLMUsageOut,
)
from ..services import admin_service

# Every route here is platform-operator-only, never tenant-scoped -- gated
# once at the router level so a new route can't be added and accidentally
# left unprotected.
router = APIRouter(prefix="/api/admin", tags=["admin"], dependencies=[Depends(require_platform_admin)])


@router.get("/overview", response_model=AdminOverviewOut)
def get_overview(db: Session = Depends(get_db)):
    return admin_service.get_platform_overview(db)


@router.get("/businesses", response_model=AdminBusinessListOut)
def list_businesses(
    q: Optional[str] = None,
    plan: Optional[str] = None,
    status: Optional[str] = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
):
    return admin_service.list_businesses(db, q=q, plan=plan, status=status, page=page, page_size=page_size)


@router.get("/businesses/{business_id}", response_model=AdminBusinessDetailOut)
def get_business(business_id: str, db: Session = Depends(get_db)):
    detail = admin_service.get_business_detail(db, business_id)
    if not detail:
        raise HTTPException(status_code=404, detail="Business not found")
    return detail


@router.patch("/businesses/{business_id}/plan", response_model=AdminBusinessDetailOut)
def set_business_plan(business_id: str, body: AdminBusinessPlanUpdate, db: Session = Depends(get_db)):
    detail = admin_service.set_business_plan(db, business_id, body.plan)
    if not detail:
        raise HTTPException(status_code=404, detail="Business not found")
    return detail


@router.patch("/businesses/{business_id}/status", response_model=AdminBusinessDetailOut)
def set_business_status(business_id: str, body: AdminBusinessStatusUpdate, db: Session = Depends(get_db)):
    detail = admin_service.set_business_status(db, business_id, body.status)
    if not detail:
        raise HTTPException(status_code=404, detail="Business not found")
    return detail


@router.get("/llm-usage", response_model=AdminLLMUsageOut)
def get_llm_usage(
    business_id: Optional[str] = None,
    days: int = Query(30, ge=1, le=365),
    db: Session = Depends(get_db),
):
    return admin_service.get_llm_usage(db, business_id=business_id, days=days)
