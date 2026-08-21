import json
from typing import List
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from ..core.database import get_db
from ..core.dependencies import get_current_user
from ..models.user import User
from ..models.faq import FAQ
from ..schemas.faq import FAQCreate, FAQUpdate, FAQOut
from ..rag.embeddings import embed_query

router = APIRouter(prefix="/api/faqs", tags=["faqs"])


@router.get("", response_model=List[FAQOut])
def list_faqs(current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return db.query(FAQ).filter(FAQ.business_id == current_user.business_id).all()


@router.post("", response_model=FAQOut)
def create_faq(
    body: FAQCreate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    faq = FAQ(business_id=current_user.business_id, **body.model_dump())
    faq.embedding_json = json.dumps(embed_query(faq.question))
    db.add(faq)
    db.commit()
    db.refresh(faq)
    return faq


@router.patch("/{faq_id}", response_model=FAQOut)
def update_faq(
    faq_id: str,
    body: FAQUpdate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    faq = db.query(FAQ).filter(FAQ.id == faq_id, FAQ.business_id == current_user.business_id).first()
    if not faq:
        raise HTTPException(status_code=404, detail="FAQ not found")
    updates = body.model_dump(exclude_none=True)
    for field, val in updates.items():
        setattr(faq, field, val)
    if "question" in updates:
        faq.embedding_json = json.dumps(embed_query(faq.question))
    db.commit()
    db.refresh(faq)
    return faq


@router.delete("/{faq_id}")
def delete_faq(
    faq_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    faq = db.query(FAQ).filter(FAQ.id == faq_id, FAQ.business_id == current_user.business_id).first()
    if not faq:
        raise HTTPException(status_code=404, detail="FAQ not found")
    db.delete(faq)
    db.commit()
    return {"ok": True}
