from typing import Optional
from decimal import Decimal
from datetime import datetime
from uuid import UUID
from pydantic import BaseModel, field_validator

# Same gap, same fix as schemas/faq.py's _not_blank: a bare `str` name field
# let the dashboard's "Add" form create a nameless product on an empty
# Save click, with no validation error anywhere.


class ProductCreate(BaseModel):
    name: str
    description: Optional[str] = None
    price: Optional[Decimal] = None
    currency: str = "USD"
    image_url: Optional[str] = None
    category: Optional[str] = None

    @field_validator("name")
    @classmethod
    def _not_blank(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("This field can't be empty.")
        return v


class ProductUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    price: Optional[Decimal] = None
    currency: Optional[str] = None
    image_url: Optional[str] = None
    category: Optional[str] = None
    is_active: Optional[bool] = None

    @field_validator("name")
    @classmethod
    def _not_blank(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return v
        v = v.strip()
        if not v:
            raise ValueError("This field can't be empty.")
        return v


class ProductOut(BaseModel):
    id: UUID
    business_id: UUID
    name: str
    description: Optional[str]
    price: Optional[Decimal]
    currency: str
    image_url: Optional[str]
    category: Optional[str]
    is_active: bool
    seo_title: Optional[str] = None
    meta_description: Optional[str] = None
    created_at: datetime

    class Config:
        from_attributes = True
