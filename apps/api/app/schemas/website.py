from typing import Optional
from datetime import datetime
from uuid import UUID
from pydantic import BaseModel


class WebsiteCreate(BaseModel):
    domain: str
    label: Optional[str] = None


class WebsiteOut(BaseModel):
    id: UUID
    business_id: UUID
    domain: str
    label: Optional[str]
    created_at: datetime

    class Config:
        from_attributes = True
