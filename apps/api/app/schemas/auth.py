from uuid import UUID
from pydantic import BaseModel, EmailStr, field_validator
from ..core.countries import COUNTRY_CODES


class RegisterRequest(BaseModel):
    business_name: str
    business_slug: str
    industry: str = "other"
    full_name: str
    email: EmailStr
    password: str
    # GDPR Phase 3. Deliberately no defaults on the three required fields: a
    # client that omits them gets a 422 just like one that sends false, so
    # the Register form's checkboxes can't be bypassed by calling the API
    # directly. marketing_opt_in defaults to False (never pre-ticked).
    country: str
    terms_accepted: bool  # Terms of Service AND the DPA (one checkbox)
    age_confirmed: bool  # 18+ and signing up on behalf of a business
    marketing_opt_in: bool = False

    @field_validator("password")
    @classmethod
    def _password_strength(cls, v: str) -> str:
        if len(v) < 10:
            raise ValueError("Password must be at least 10 characters long")
        return v

    @field_validator("country")
    @classmethod
    def _known_country(cls, v: str) -> str:
        code = v.strip().upper()
        if code not in COUNTRY_CODES:
            raise ValueError("Select a valid country")
        return code

    @field_validator("terms_accepted")
    @classmethod
    def _terms_required(cls, v: bool) -> bool:
        if v is not True:
            raise ValueError("You must accept the Terms of Service and the Data Processing Agreement")
        return v

    @field_validator("age_confirmed")
    @classmethod
    def _age_required(cls, v: bool) -> bool:
        if v is not True:
            raise ValueError("You must confirm you are 18 or older and signing up on behalf of a business")
        return v


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class ForgotPasswordRequest(BaseModel):
    email: EmailStr


class ResetPasswordRequest(BaseModel):
    token: str
    new_password: str

    @field_validator("new_password")
    @classmethod
    def _password_strength(cls, v: str) -> str:
        if len(v) < 10:
            raise ValueError("Password must be at least 10 characters long")
        return v


class MessageResponse(BaseModel):
    message: str


class UserOut(BaseModel):
    id: UUID
    email: str
    full_name: str
    role: str
    business_id: UUID
    is_platform_admin: bool = False

    class Config:
        from_attributes = True
