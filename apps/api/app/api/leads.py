from typing import List
from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request
from sqlalchemy.orm import Session
from ..core.database import get_db
from ..core.dependencies import get_current_user
from ..core.limiter import limiter
from ..models.user import User
from ..models.lead import Lead
from ..models.business import Business, BusinessSettings
from ..models.conversation import Conversation
from ..notifications import notify_new_lead
from ..schemas.lead import LeadCreate, LeadUpdate, LeadOut

router = APIRouter(prefix="/api/leads", tags=["leads"])


@router.get("", response_model=List[LeadOut])
def list_leads(current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return (
        db.query(Lead)
        .filter(Lead.business_id == current_user.business_id)
        .order_by(Lead.created_at.desc())
        .all()
    )


@router.post("", response_model=LeadOut)
@limiter.limit("10/minute")
def create_lead(request: Request, body: LeadCreate, background_tasks: BackgroundTasks, db: Session = Depends(get_db)):
    conversation_id = None
    if body.session_id:
        conv = db.query(Conversation).filter(
            Conversation.session_id == body.session_id,
            Conversation.business_id == body.business_id,
        ).first()
        if conv:
            conversation_id = conv.id

    lead = Lead(
        business_id=body.business_id,
        conversation_id=conversation_id,
        name=body.name,
        email=body.email,
        phone=body.phone,
        message=body.message,
    )
    db.add(lead)
    db.commit()
    db.refresh(lead)

    business = db.query(Business).filter(Business.id == body.business_id).first()
    biz_settings = db.query(BusinessSettings).filter(BusinessSettings.business_id == body.business_id).first()
    if business and biz_settings and biz_settings.contact_email:
        background_tasks.add_task(notify_new_lead, business.name, biz_settings.contact_email, lead)

    return lead


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
