from fastapi import APIRouter, BackgroundTasks, Depends, Request, Response
from sqlalchemy.orm import Session
from ..core.config import settings
from ..core.database import get_db
from ..core.dependencies import AUTH_COOKIE_NAME, get_current_user, is_platform_admin
from ..core.limiter import limiter
from ..models.user import User
from ..notifications import notify_password_reset
from ..schemas.auth import (
    RegisterRequest,
    LoginRequest,
    ForgotPasswordRequest,
    ResetPasswordRequest,
    MessageResponse,
    UserOut,
)
from ..services import auth_service

router = APIRouter(prefix="/api/auth", tags=["auth"])


def _user_out(user: User) -> UserOut:
    out = UserOut.model_validate(user)
    out.is_platform_admin = is_platform_admin(user)
    return out


def _set_auth_cookie(response: Response, token: str) -> None:
    # httpOnly so an XSS on the dashboard can't read the token out of
    # localStorage/JS; SameSite=Lax means the browser withholds it on
    # cross-site POST/PUT/DELETE requests, which is the main CSRF vector
    # for a cookie-based session.
    response.set_cookie(
        key=AUTH_COOKIE_NAME,
        value=token,
        httponly=True,
        secure=not settings.debug,
        samesite="lax",
        max_age=settings.access_token_expire_minutes * 60,
        path="/",
    )


@router.post("/register", response_model=UserOut)
@limiter.limit("10/hour")
def register(request: Request, req: RegisterRequest, response: Response, db: Session = Depends(get_db)):
    user, token = auth_service.register(db, req)
    _set_auth_cookie(response, token)
    return _user_out(user)


@router.post("/login", response_model=UserOut)
@limiter.limit("10/minute")
def login(request: Request, req: LoginRequest, response: Response, db: Session = Depends(get_db)):
    user, token = auth_service.login(db, req)
    _set_auth_cookie(response, token)
    return _user_out(user)


@router.get("/me", response_model=UserOut)
def me(current_user: User = Depends(get_current_user)):
    return _user_out(current_user)


@router.post("/logout", response_model=MessageResponse)
def logout(response: Response):
    response.delete_cookie(AUTH_COOKIE_NAME, path="/")
    return MessageResponse(message="Logged out.")


@router.post("/forgot-password", response_model=MessageResponse)
@limiter.limit("5/hour")
def forgot_password(
    request: Request,
    req: ForgotPasswordRequest,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
):
    result = auth_service.request_password_reset(db, req.email)
    if result:
        user, raw_token = result
        background_tasks.add_task(notify_password_reset, user.email, user.full_name, raw_token)
    # Always the same message whether or not the email is registered, so this
    # endpoint can't be used to enumerate accounts.
    return MessageResponse(message="If an account exists for that email, we've sent a password reset link.")


@router.post("/reset-password", response_model=MessageResponse)
@limiter.limit("10/hour")
def reset_password(request: Request, req: ResetPasswordRequest, db: Session = Depends(get_db)):
    auth_service.reset_password(db, req.token, req.new_password)
    return MessageResponse(message="Your password has been reset. You can now sign in.")
