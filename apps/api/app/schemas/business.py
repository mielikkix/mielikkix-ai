from typing import Optional, Dict, List
from uuid import UUID
from pydantic import BaseModel


class DayHours(BaseModel):
    open: str  # "HH:MM", 24-hour
    close: str  # "HH:MM", 24-hour


class BusinessHours(BaseModel):
    """One entry per weekday; a day left unset (or explicitly null in a
    PATCH) means closed that day. Read by Booking Assistant's
    _business_hours_window (app/api/agents_booking.py) to compute a real
    tenant's open slots, replacing the Phase 1-3 hardcoded Mon-Fri window
    it still falls back to for business_id=None calls."""

    monday: Optional[DayHours] = None
    tuesday: Optional[DayHours] = None
    wednesday: Optional[DayHours] = None
    thursday: Optional[DayHours] = None
    friday: Optional[DayHours] = None
    saturday: Optional[DayHours] = None
    sunday: Optional[DayHours] = None


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
    business_hours: Optional[BusinessHours]
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
    # Always sent whole (all seven days) by the Settings UI, same
    # full-replace convention as `languages` below -- not merged with
    # whatever was already stored.
    business_hours: Optional[BusinessHours] = None
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
