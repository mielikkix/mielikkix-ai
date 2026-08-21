from typing import Optional, Any, Dict, List
from uuid import UUID
from pydantic import BaseModel


class BusinessOut(BaseModel):
    id: UUID
    name: str
    slug: str
    industry: str
    logo_url: Optional[str]
    primary_color: str
    plan: str
    status: str

    class Config:
        from_attributes = True


class BusinessSettingsOut(BaseModel):
    tone: str
    welcome_message: str
    fallback_message: str
    fallback_messages: Dict[str, str]
    business_hours: Any
    contact_email: Optional[str]
    contact_phone: Optional[str]
    languages: List[str]
    llm_provider: str
    llm_model: Optional[str]

    class Config:
        from_attributes = True


class PublicBusinessSettingsOut(BaseModel):
    welcome_message: str
    languages: List[str]
    primary_color: str

    class Config:
        from_attributes = True


class BusinessSettingsUpdate(BaseModel):
    tone: Optional[str] = None
    welcome_message: Optional[str] = None
    fallback_message: Optional[str] = None
    fallback_messages: Optional[Dict[str, str]] = None
    business_hours: Optional[Any] = None
    contact_email: Optional[str] = None
    contact_phone: Optional[str] = None
    languages: Optional[List[str]] = None
    llm_provider: Optional[str] = None
    llm_model: Optional[str] = None


class BusinessUpdate(BaseModel):
    name: Optional[str] = None
    logo_url: Optional[str] = None
    primary_color: Optional[str] = None
    industry: Optional[str] = None
