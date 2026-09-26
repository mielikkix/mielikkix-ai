from typing import Optional, Dict, List
from urllib.parse import urlparse
from uuid import UUID
from pydantic import BaseModel, StrictInt, field_validator

from ..core.legal import (
    CONVERSATION_RETENTION_DEFAULT_DAYS,
    CONVERSATION_RETENTION_MAX_DAYS,
    CONVERSATION_RETENTION_MIN_DAYS,
)


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
    privacy_policy_url: Optional[str] = None
    conversation_retention_days: int = CONVERSATION_RETENTION_DEFAULT_DAYS

    class Config:
        from_attributes = True


class PublicBusinessSettingsOut(BaseModel):
    welcome_message: str
    languages: List[str]
    primary_color: str
    # Linked from the widget's AI notice; null = only Mielikkix's own link shows.
    privacy_policy_url: Optional[str] = None

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
    # "" clears it (exclude_none would skip a None).
    privacy_policy_url: Optional[str] = None
    conversation_retention_days: Optional[StrictInt] = None

    @field_validator("privacy_policy_url")
    @classmethod
    def _https_url(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return v
        v = v.strip()
        if v == "":
            return ""
        parsed = urlparse(v)
        if parsed.scheme not in ("https", "http") or not parsed.netloc or " " in v:
            raise ValueError("Enter a full web address, e.g. https://yourbusiness.com/privacy")
        return v

    @field_validator("conversation_retention_days")
    @classmethod
    def _retention_bounds(cls, v: Optional[int]) -> Optional[int]:
        if v is None:
            return v
        if not CONVERSATION_RETENTION_MIN_DAYS <= v <= CONVERSATION_RETENTION_MAX_DAYS:
            raise ValueError(
                f"Conversation retention must be between {CONVERSATION_RETENTION_MIN_DAYS} and "
                f"{CONVERSATION_RETENTION_MAX_DAYS} days"
            )
        return v


class BusinessUpdate(BaseModel):
    name: Optional[str] = None
    logo_url: Optional[str] = None
    primary_color: Optional[str] = None
    industry: Optional[str] = None
