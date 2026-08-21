from uuid import UUID
from pydantic import BaseModel, EmailStr, field_validator


class RegisterRequest(BaseModel):
    business_name: str
    business_slug: str
    industry: str = "other"
    full_name: str
    email: EmailStr
    password: str

    @field_validator("password")
    @classmethod
    def _password_strength(cls, v: str) -> str:
        if len(v) < 10:
            raise ValueError("Password must be at least 10 characters long")
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
