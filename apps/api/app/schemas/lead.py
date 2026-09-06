import re
from typing import Optional
from datetime import datetime
from uuid import UUID
from pydantic import BaseModel, EmailStr, Field, field_validator, model_validator

# Loose on purpose -- accepts spaces, dashes, parens, and an optional leading
# +, but requires at least 7 digits so obvious garbage ("abc-@@@") is
# rejected without false-negatives on real international phone formats.
PHONE_RE = re.compile(r"^\+?[0-9()\-.\s]{7,20}$")


class LeadCreate(BaseModel):
    business_id: str
    # Kept required for backward compatibility with the live Chat Widget
    # (apps/dashboard/src/widget/LeadForm.tsx), which has always sent a
    # single `name` field for every tenant's own end-customer leads and
    # must keep working unmodified. The marketing site's "Book a Free
    # Demo" form (website/src/pages/demo.astro) instead sends
    # first_name/last_name below AND a derived `name`
    # (see that page's demo-form.js) so both shapes satisfy this the same way.
    name: str
    email: Optional[EmailStr] = None
    phone: Optional[str] = None
    message: Optional[str] = None
    session_id: Optional[str] = None

    # Marketing-lead-only fields below -- all optional at the schema level
    # (not required-by-validation) for the same backward-compatibility
    # reason as `name` above: the generic chat-widget lead payload never
    # sends any of these, and making them required here would 422 every
    # live Chat Widget submission across every tenant. The marketing
    # form's own HTML `required` attributes (see demo.astro) are what
    # actually enforces "required" for ITS fields; the backend just stores
    # whatever it's given and only acts on these when a lead belongs to
    # settings.mailchimp_sync_business_id (see lead_service.py).
    first_name: Optional[str] = Field(default=None, max_length=100)
    last_name: Optional[str] = Field(default=None, max_length=100)
    company: Optional[str] = Field(default=None, max_length=200)
    industry: Optional[str] = Field(default=None, max_length=100)
    interest: Optional[str] = Field(default=None, max_length=100)
    source: Optional[str] = Field(default=None, max_length=50)
    marketing_consent: bool = False

    @field_validator("phone")
    @classmethod
    def validate_phone(cls, v: Optional[str]) -> Optional[str]:
        if v and not PHONE_RE.match(v):
            raise ValueError("Enter a valid phone number")
        return v

    @field_validator("name", "first_name", "last_name", "company", "message")
    @classmethod
    def strip_whitespace(cls, v: Optional[str]) -> Optional[str]:
        return v.strip() if isinstance(v, str) else v

    @model_validator(mode="after")
    def _require_non_empty_name(self) -> "LeadCreate":
        if not self.name:
            raise ValueError("name must not be empty")
        return self


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
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    company: Optional[str] = None
    industry: Optional[str] = None
    interest: Optional[str] = None
    source: Optional[str] = None
    marketing_consent: bool = False
    mailchimp_synced: bool = False
    mailchimp_last_synced_at: Optional[datetime] = None

    class Config:
        from_attributes = True


class LeadCreateResponse(BaseModel):
    """Public response shape for POST /api/leads -- deliberately never the
    raw Lead row (no internal id, no Mailchimp response data), per this
    integration's design brief: a Mailchimp failure must be invisible to
    the visitor as long as the local DB save succeeded (see
    lead_service.sync_lead_to_mailchimp)."""

    success: bool
    message: str
