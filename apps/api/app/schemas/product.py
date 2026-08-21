from typing import Optional
from decimal import Decimal
from datetime import datetime
from uuid import UUID
from pydantic import BaseModel


class ProductCreate(BaseModel):
    name: str
    description: Optional[str] = None
    price: Optional[Decimal] = None
    currency: str = "USD"
    image_url: Optional[str] = None
    category: Optional[str] = None


class ProductUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    price: Optional[Decimal] = None
    currency: Optional[str] = None
    image_url: Optional[str] = None
    category: Optional[str] = None
    is_active: Optional[bool] = None


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
    created_at: datetime

    class Config:
        from_attributes = True
