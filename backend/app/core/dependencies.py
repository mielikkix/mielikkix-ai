import uuid
from fastapi import Depends, HTTPException, Request, status
from sqlalchemy.orm import Session
from jose import JWTError
from .config import settings
from .database import get_db
from .security import decode_token
from ..models.user import User
from ..models.business import Business

AUTH_COOKIE_NAME = "access_token"


def get_current_user(
    request: Request,
    db: Session = Depends(get_db),
) -> User:
    token = request.cookies.get(AUTH_COOKIE_NAME)
    if not token:
        # Fallback for direct/API-key-style access (see the plan's
        # api-access-addon) — the dashboard itself only ever uses the
        # httpOnly cookie set by /api/auth/login.
        auth_header = request.headers.get("authorization", "")
        if auth_header.lower().startswith("bearer "):
            token = auth_header[7:]
    if not token:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Not authenticated")
    try:
        payload = decode_token(token)
        raw_user_id = payload.get("sub")
        if not raw_user_id:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token")
        # The JWT "sub" claim is always a plain string. psycopg2 happily
        # compares that against a UUID column, but that's Postgres being
        # lenient, not a guarantee -- coerce explicitly so this works the
        # same on every backend (and rejects malformed tokens up front
        # instead of a confusing query-level error).
        user_id = uuid.UUID(raw_user_id)
    except (JWTError, ValueError):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token")

    user = db.query(User).filter(User.id == user_id, User.is_active == True).first()
    if not user:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User not found")
    return user


def get_current_business(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> Business:
    business = db.query(Business).filter(Business.id == current_user.business_id).first()
    if not business:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Business not found")
    return business


def is_platform_admin(user: User) -> bool:
    """Whether this user is the platform operator (AgentNexus itself), not a
    tenant. Deliberately config-driven (PLATFORM_ADMIN_EMAILS), not a DB
    column -- see the comment on that setting in core/config.py."""
    return user.email.lower() in settings.platform_admin_emails_list


def require_platform_admin(current_user: User = Depends(get_current_user)) -> User:
    if not is_platform_admin(current_user):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not authorized")
    return current_user
