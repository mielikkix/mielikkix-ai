"""Account self-service: "Privacy & data" in dashboard Settings (GDPR Phase 4).

Every route here stays reachable while a Terms/DPA re-acceptance is pending
(see core/dependencies.REACCEPTANCE_EXEMPT_PREFIXES): a user must always be
able to export their data, delete their account or change their marketing
choice without first agreeing to new terms.
"""
import json
from datetime import datetime
from typing import Literal, Optional

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request
from fastapi.responses import Response
from pydantic import BaseModel
from sqlalchemy.orm import Session

from ..core.database import get_db
from ..core.dependencies import get_current_user
from ..core.legal import CONSENT_DPA, CONSENT_TERMS, SOURCE_SETTINGS
from ..core.limiter import limiter
from ..models.business import Business
from ..models.user import User
from ..notifications import notify_account_deletion_cancelled, notify_account_deletion_scheduled
from ..services import account_service, consent_service

router = APIRouter(prefix="/api/account", tags=["account"])


class ConsentOut(BaseModel):
    type: str
    document_version: Optional[str]
    granted: bool
    granted_at: datetime
    withdrawn_at: Optional[datetime]
    source: str

    class Config:
        from_attributes = True


class PrivacyOut(BaseModel):
    # Here (not only via /businesses/me) because that route is blocked while a
    # re-acceptance is pending, and the delete form needs the name to confirm.
    business_name: str
    marketing_emails: bool
    pending_acceptance: list[str]
    deletion_requested_at: Optional[datetime]
    deletion_scheduled_for: Optional[datetime]
    is_owner: bool
    history: list[ConsentOut]


class MarketingIn(BaseModel):
    subscribed: bool


class AcceptIn(BaseModel):
    documents: list[Literal["terms", "dpa"]]


class DeletionIn(BaseModel):
    confirm_business_name: str


def _privacy(db: Session, user: User) -> PrivacyOut:
    business = db.get(Business, user.business_id)
    return PrivacyOut(
        business_name=business.name,
        marketing_emails=consent_service.has_marketing_consent(db, user.id),
        pending_acceptance=consent_service.pending_documents(db, user.id),
        deletion_requested_at=business.deletion_requested_at,
        deletion_scheduled_for=business.deletion_scheduled_for,
        is_owner=user.role == "owner",
        history=[ConsentOut.model_validate(r) for r in consent_service.history(db, user.id)],
    )


@router.get("/privacy", response_model=PrivacyOut)
def get_privacy(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return _privacy(db, user)


@router.put("/marketing", response_model=PrivacyOut)
def set_marketing(body: MarketingIn, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    consent_service.set_marketing_consent(db, user.id, granted=body.subscribed, source=SOURCE_SETTINGS)
    return _privacy(db, user)


@router.post("/consents/accept", response_model=PrivacyOut)
def accept_documents(
    request: Request, body: AcceptIn, user: User = Depends(get_current_user), db: Session = Depends(get_db)
):
    pending = consent_service.pending_documents(db, user.id)
    missing = [d for d in pending if d not in body.documents]
    if missing:
        raise HTTPException(status_code=422, detail=f"Please accept all updated documents: {', '.join(missing)}.")
    ip = request.client.host if request.client else None
    consent_service.accept_documents(db, user.id, [d for d in (CONSENT_TERMS, CONSENT_DPA) if d in pending], consent_service.hash_ip(ip))
    return _privacy(db, user)


@router.get("/export")
@limiter.limit("10/hour")
def export(request: Request, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    data = account_service.export_data(db, user)
    filename = f"mielikkix-export-{datetime.now().strftime('%Y%m%d')}.json"
    return Response(
        content=json.dumps(data, ensure_ascii=False, indent=2),
        media_type="application/json",
        headers={"Content-Disposition": f'attachment; filename="{filename}"', "Cache-Control": "no-store"},
    )


@router.post("/deletion", response_model=PrivacyOut)
@limiter.limit("10/hour")
def request_deletion(
    request: Request,
    body: DeletionIn,
    background_tasks: BackgroundTasks,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    already = db.get(Business, user.business_id).deletion_scheduled_for is not None
    business = account_service.request_deletion(db, user, body.confirm_business_name)
    if not already:
        background_tasks.add_task(notify_account_deletion_scheduled, user.email, user.full_name, business.name, business.deletion_scheduled_for)
    return _privacy(db, user)


@router.delete("/deletion", response_model=PrivacyOut)
def cancel_deletion(background_tasks: BackgroundTasks, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    was_scheduled = db.get(Business, user.business_id).deletion_scheduled_for is not None
    business = account_service.cancel_deletion(db, user)
    if was_scheduled:
        background_tasks.add_task(notify_account_deletion_cancelled, user.email, user.full_name, business.name)
    return _privacy(db, user)
