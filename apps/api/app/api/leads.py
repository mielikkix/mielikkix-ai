import logging
from typing import List
from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request
from sqlalchemy.orm import Session
from ..core.database import get_db
from ..core.dependencies import get_current_user
from ..core.limiter import limiter
from ..models.user import User
from ..models.lead import Lead
from ..models.business import Business, BusinessSettings
from ..notifications import notify_new_lead
from ..schemas.lead import LeadCreate, LeadUpdate, LeadOut, LeadCreateResponse
from ..services import lead_service

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/leads", tags=["leads"])


@router.get("", response_model=List[LeadOut])
def list_leads(current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return (
        db.query(Lead)
        .filter(Lead.business_id == current_user.business_id)
        .order_by(Lead.created_at.desc())
        .all()
    )


@router.post("", response_model=LeadCreateResponse, status_code=201)
@limiter.limit("10/minute")
def create_lead(request: Request, body: LeadCreate, background_tasks: BackgroundTasks, db: Session = Depends(get_db)):
    is_new = not (
        lead_service.is_marketing_business(body.business_id)
        and body.email
        and db.query(Lead)
        .filter(Lead.business_id == body.business_id, Lead.email == body.email.strip().lower())
        .first()
    )
    lead = lead_service.create_or_update_lead(db, body)
    logger.info("Lead %s for business %s", "created" if is_new else "updated", lead.business_id)

    # Mailchimp sync is scheduled BEFORE the notify_new_lead task below,
    # deliberately: Starlette's BackgroundTasks runs its tasks in order and
    # stops at the first one that raises, so a notify_new_lead failure
    # (e.g. a misconfigured/unreachable transactional email provider)
    # would otherwise silently prevent every task queued after it from
    # ever running. sync_lead_to_mailchimp is written to never raise past
    # itself (see its own docstring), so it's the safe one to put first.
    if lead_service.is_marketing_business(body.business_id):
        background_tasks.add_task(lead_service.sync_lead_to_mailchimp, db, lead)

    business = db.query(Business).filter(Business.id == body.business_id).first()
    biz_settings = db.query(BusinessSettings).filter(BusinessSettings.business_id == body.business_id).first()
    if business and biz_settings and biz_settings.contact_email:
        background_tasks.add_task(notify_new_lead, business.name, biz_settings.contact_email, lead)

    return LeadCreateResponse(
        success=True, message="Thank you. Your demo request has been received."
    )


@router.patch("/{lead_id}", response_model=LeadOut)
def update_lead(
    lead_id: str,
    body: LeadUpdate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    lead = db.query(Lead).filter(
        Lead.id == lead_id, Lead.business_id == current_user.business_id
    ).first()
    if not lead:
        raise HTTPException(status_code=404, detail="Lead not found")
    lead.status = body.status
    db.commit()
    db.refresh(lead)
    return lead


@router.post("/{lead_id}/sync-mailchimp", response_model=LeadOut)
async def sync_lead_mailchimp(
    lead_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Manual retry for a lead whose automatic Mailchimp sync failed (see
    lead_service.sync_lead_to_mailchimp) -- authenticated + tenant-scoped
    the same way GET/PATCH above are. In practice only ever meaningful for
    settings.mailchimp_sync_business_id's own leads (sync_lead_to_mailchimp
    itself is a no-op for anything else, since is_marketing_business
    gates it), but scoped to current_user.business_id like every other
    lead route here rather than requiring platform-admin, since there's
    nothing tenant-sensitive about retrying your OWN lead's own sync."""
    lead = db.query(Lead).filter(
        Lead.id == lead_id, Lead.business_id == current_user.business_id
    ).first()
    if not lead:
        raise HTTPException(status_code=404, detail="Lead not found")
    logger.info("Mailchimp retry requested for lead %s", lead.id)
    await lead_service.sync_lead_to_mailchimp(db, lead)
    db.refresh(lead)
    return lead
