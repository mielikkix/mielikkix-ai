from typing import Optional
from datetime import datetime
from uuid import UUID
from pydantic import BaseModel


class FAQCreate(BaseModel):
    question: str
    answer: str
    category: Optional[str] = None


class FAQUpdate(BaseModel):
    question: Optional[str] = None
    answer: Optional[str] = None
    category: Optional[str] = None
    is_active: Optional[bool] = None


class FAQOut(BaseModel):
    id: UUID
    business_id: UUID
    question: str
    answer: str
    category: Optional[str]
    is_active: bool
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True
