from typing import Optional
from datetime import datetime
from uuid import UUID
from pydantic import BaseModel, field_validator

# A bare `str` field accepts "" and "   " just as happily as real content --
# confirmed live via the dashboard's "Add FAQ" form: clicking Save with both
# fields empty silently created a blank FAQ (empty question AND answer),
# with no error anywhere. Stripped, non-empty validators on both fields
# (create and, for the same reason, update -- the edit form has the exact
# same gap) close that off at the one place every request has to pass
# through, rather than trusting the dashboard's own client-side checks.


class FAQCreate(BaseModel):
    question: str
    answer: str
    category: Optional[str] = None

    @field_validator("question", "answer")
    @classmethod
    def _not_blank(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("This field can't be empty.")
        return v


class FAQUpdate(BaseModel):
    question: Optional[str] = None
    answer: Optional[str] = None
    category: Optional[str] = None
    is_active: Optional[bool] = None

    @field_validator("question", "answer")
    @classmethod
    def _not_blank(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return v
        v = v.strip()
        if not v:
            raise ValueError("This field can't be empty.")
        return v


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
