import hashlib
import re
import secrets
from datetime import datetime, timedelta, timezone
from typing import Optional
from sqlalchemy.orm import Session
from fastapi import HTTPException, status
from ..models.business import Business, BusinessSettings
from ..models.password_reset_token import PasswordResetToken
from ..models.user import User
from ..schemas.auth import RegisterRequest, LoginRequest
from ..core.security import hash_password, verify_password, create_access_token

RESET_TOKEN_TTL = timedelta(hours=1)


def _hash_token(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def register(db: Session, req: RegisterRequest) -> tuple[User, str]:
    if db.query(User).filter(User.email == req.email).first():
        raise HTTPException(status_code=400, detail="Email already registered")

    slug = re.sub(r"[^a-z0-9-]", "-", req.business_slug.lower().strip())
    if db.query(Business).filter(Business.slug == slug).first():
        raise HTTPException(status_code=400, detail="Business slug already taken")

    business = Business(name=req.business_name, slug=slug, industry=req.industry)
    db.add(business)
    db.flush()

    biz_settings = BusinessSettings(business_id=business.id)
    db.add(biz_settings)

    user = User(
        business_id=business.id,
        email=req.email,
        hashed_password=hash_password(req.password),
        full_name=req.full_name,
        role="owner",
    )
    db.add(user)
    db.commit()
    db.refresh(user)

    token = create_access_token({"sub": str(user.id), "business_id": str(business.id)})
    return user, token


def login(db: Session, req: LoginRequest) -> tuple[User, str]:
    user = db.query(User).filter(User.email == req.email, User.is_active == True).first()
    if not user or not verify_password(req.password, user.hashed_password):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials")

    token = create_access_token({"sub": str(user.id), "business_id": str(user.business_id)})
    return user, token


def request_password_reset(db: Session, email: str) -> Optional[tuple[User, str]]:
    """Returns (user, raw_token) to email, or None if no such active user.

    Callers must always return the same generic response regardless of which
    case this is — never let the forgot-password endpoint reveal whether an
    email is registered.
    """
    user = db.query(User).filter(User.email == email, User.is_active == True).first()
    if not user:
        return None

    raw_token = secrets.token_urlsafe(32)
    reset = PasswordResetToken(
        user_id=user.id,
        token_hash=_hash_token(raw_token),
        expires_at=datetime.now(timezone.utc) + RESET_TOKEN_TTL,
    )
    db.add(reset)
    db.commit()
    return user, raw_token


def reset_password(db: Session, token: str, new_password: str) -> None:
    record = (
        db.query(PasswordResetToken)
        .filter(PasswordResetToken.token_hash == _hash_token(token))
        .first()
    )
    if (
        not record
        or record.used_at is not None
        or record.expires_at < datetime.now(timezone.utc)
    ):
        raise HTTPException(status_code=400, detail="Invalid or expired reset link")

    user = db.query(User).filter(User.id == record.user_id).first()
    if not user:
        raise HTTPException(status_code=400, detail="Invalid or expired reset link")

    user.hashed_password = hash_password(new_password)
    record.used_at = datetime.now(timezone.utc)
    db.commit()
