import re
from typing import Optional
from datetime import datetime
from uuid import UUID
from pydantic import BaseModel, EmailStr, field_validator

# Loose on purpose -- accepts spaces, dashes, parens, and an optional leading
# +, but requires at least 7 digits so obvious garbage ("abc-@@@") is
# rejected without false-negatives on real international phone formats.
PHONE_RE = re.compile(r"^\+?[0-9()\-.\s]{7,20}$")


class LeadCreate(BaseModel):
    business_id: str
    name: str
    email: Optional[EmailStr] = None
    phone: Optional[str] = None
    message: Optional[str] = None
    session_id: Optional[str] = None

    @field_validator("phone")
    @classmethod
    def validate_phone(cls, v: Optional[str]) -> Optional[str]:
        if v and not PHONE_RE.match(v):
            raise ValueError("Enter a valid phone number")
        return v


class LeadUpdate(BaseModel):
    status: str


class LeadOut(BaseModel):
    id: UUID
    business_id: UUID
    name: str
    email: Optional[str]
    phone: Optional[str]
    message: Optional[str]
    status: str
    created_at: datetime

    class Config:
        from_attributes = True
