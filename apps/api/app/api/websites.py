from typing import List
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from ..core.database import get_db
from ..core.dependencies import get_current_user, get_current_business
from ..models.user import User
from ..models.business import Business
from ..models.website import BusinessWebsite
from ..schemas.website import WebsiteCreate, WebsiteOut
from ..services import plan_service

router = APIRouter(prefix="/api/websites", tags=["websites"])


@router.get("", response_model=List[WebsiteOut])
def list_websites(current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return db.query(BusinessWebsite).filter(
        BusinessWebsite.business_id == current_user.business_id
    ).all()


@router.post("", response_model=WebsiteOut)
def add_website(
    body: WebsiteCreate,
    current_user: User = Depends(get_current_user),
    business: Business = Depends(get_current_business),
    db: Session = Depends(get_db),
):
    plan_service.check_website_limit(db, business)
    website = BusinessWebsite(business_id=business.id, domain=body.domain, label=body.label)
    db.add(website)
    db.commit()
    db.refresh(website)
    return website


@router.delete("/{website_id}")
def delete_website(
    website_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    website = db.query(BusinessWebsite).filter(
        BusinessWebsite.id == website_id, BusinessWebsite.business_id == current_user.business_id
    ).first()
    if not website:
        raise HTTPException(status_code=404, detail="Website not found")
    db.delete(website)
    db.commit()
    return {"ok": True}
