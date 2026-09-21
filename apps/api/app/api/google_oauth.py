"""SEO Audit & Optimization, Stage 12: real per-tenant Google Analytics +
Search Console OAuth (apps/agents/seo-audit/CLAUDE.md's "Professional
tier roadmap"). Structurally identical to app/api/calendar_oauth.py's own
Authorization Code flow -- same signed-state/verify/exchange shape, same
reasons for each of the OAUTHLIB_* env flags below -- just against a
different connection row (SeoGoogleConnection) and two read-only reporting
scopes instead of Calendar's.

Flow, end to end:
  1. GET /authorize -- business clicks "Connect Google" on the SEO page.
     Builds a signed `state` and 302s to Google's consent screen, asking
     for BOTH the Analytics and Search Console read-only scopes in one
     consent (see this agent's CLAUDE.md "Pricing" section's "one shared
     Google OAuth app" decision).
  2. The business owner signs in to THEIR OWN Google account and approves.
  3. GET /callback -- verifies `state`, exchanges `code` for tokens,
     encrypts the refresh token, upserts SeoGoogleConnection.
  4. Browser lands back on the dashboard SEO page
     (?google=connected or ?google=error).

Connecting alone isn't enough to fetch anything -- see
SeoGoogleConnection's own docstring for why analytics_property_id/
search_console_site_url are set separately via PATCH /config below.
"""

import hashlib
import hmac
import logging
import os
import time

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import RedirectResponse
from google_auth_oauthlib.flow import Flow
from pydantic import BaseModel
from sqlalchemy.orm import Session
from typing import Optional

from ..core.config import settings
from ..core.database import get_db
from ..core.dependencies import get_current_business, get_current_user
from ..core.encryption import encrypt
from ..integrations.analytics_provider import ANALYTICS_SCOPE
from ..integrations.search_console_provider import SEARCH_CONSOLE_SCOPE
from ..models.business import Business
from ..models.seo_google_connection import SeoGoogleConnection
from ..models.user import User
from ..services import agent_access_service

logger = logging.getLogger(__name__)

# Same two env-flag reasons as calendar_oauth.py's own docstring (Google
# adding openid/email scopes unasked, and oauthlib refusing a plain-HTTP
# callback in local dev) -- setdefault so whichever OAuth router imports
# first "wins" harmlessly, both would set the same value anyway.
os.environ.setdefault("OAUTHLIB_RELAX_TOKEN_SCOPE", "1")
if settings.debug:
    os.environ.setdefault("OAUTHLIB_INSECURE_TRANSPORT", "1")

router = APIRouter(prefix="/api/businesses/me/google", tags=["seo-audit-google-oauth"])

_REDIRECT_PATH = "/api/businesses/me/google/callback"
_OAUTH_SCOPES = [ANALYTICS_SCOPE, SEARCH_CONSOLE_SCOPE, "https://www.googleapis.com/auth/userinfo.email"]
_STATE_TTL_SECONDS = 600


def _redirect_uri() -> str:
    return f"{settings.api_public_base_url}{_REDIRECT_PATH}"


def _sign_state(business_id: str) -> str:
    """Same HMAC-signed `business_id:timestamp` scheme as
    calendar_oauth.py's own _sign_state -- see that function's docstring."""
    payload = f"{business_id}:{int(time.time())}"
    signature = hmac.new(settings.secret_key.encode(), payload.encode(), hashlib.sha256).hexdigest()
    return f"{payload}:{signature}"


def _verify_state(state: str) -> str:
    try:
        business_id, timestamp_str, signature = state.split(":")
    except ValueError:
        raise ValueError("Malformed state")

    payload = f"{business_id}:{timestamp_str}"
    expected_signature = hmac.new(settings.secret_key.encode(), payload.encode(), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(expected_signature, signature):
        raise ValueError("Invalid state signature")
    if time.time() - int(timestamp_str) > _STATE_TTL_SECONDS:
        raise ValueError("State expired")

    return business_id


def _build_flow() -> Flow:
    redirect_uri = _redirect_uri()
    return Flow.from_client_config(
        {
            "web": {
                "client_id": settings.google_analytics_oauth_client_id,
                "client_secret": settings.google_analytics_oauth_client_secret,
                "auth_uri": "https://accounts.google.com/o/oauth2/auth",
                "token_uri": "https://oauth2.googleapis.com/token",
                "redirect_uris": [redirect_uri],
            }
        },
        scopes=_OAUTH_SCOPES,
        redirect_uri=redirect_uri,
    )


def _fetch_google_account_email(credentials) -> str | None:
    """Best-effort only, same as calendar_oauth.py's own version -- a
    failure here must never block the connection itself."""
    try:
        from googleapiclient.discovery import build

        service = build("oauth2", "v2", credentials=credentials)
        return service.userinfo().get().execute().get("email")
    except Exception:
        return None


@router.get("/authorize")
def authorize(
    current_user: User = Depends(get_current_user),
    business: Business = Depends(get_current_business),
    db: Session = Depends(get_db),
):
    agent_access_service.require_agent_access(db, business, "seo_audit_optimization")

    if not (settings.google_analytics_oauth_client_id and settings.google_analytics_oauth_client_secret):
        raise HTTPException(status_code=503, detail="Google Analytics/Search Console isn't configured on this server yet.")

    flow = _build_flow()
    auth_url, _ = flow.authorization_url(
        access_type="offline",
        prompt="consent",
        state=_sign_state(str(business.id)),
    )
    return RedirectResponse(auth_url)


@router.get("/callback")
def callback(
    request: Request,
    code: str | None = None,
    state: str | None = None,
    error: str | None = None,
    db: Session = Depends(get_db),
):
    """No auth dependency here, same reasoning as calendar_oauth.py's own
    callback: Google redirects the browser here directly, so `state` --
    not the session -- is what proves which business this belongs to."""
    error_redirect = f"{settings.frontend_url}/dashboard/seo?google=error"

    if error or not code or not state:
        return RedirectResponse(error_redirect)

    try:
        business_id = _verify_state(state)
    except ValueError:
        return RedirectResponse(error_redirect)

    try:
        flow = _build_flow()
        flow.fetch_token(authorization_response=str(request.url))
        credentials = flow.credentials
    except Exception:
        logger.exception("Google Analytics/Search Console OAuth token exchange failed for business_id=%s", business_id)
        return RedirectResponse(error_redirect)

    if not credentials.refresh_token:
        return RedirectResponse(error_redirect)

    google_account_email = _fetch_google_account_email(credentials)

    connection = db.query(SeoGoogleConnection).filter(SeoGoogleConnection.business_id == business_id).first()
    if connection is None:
        connection = SeoGoogleConnection(business_id=business_id)
        db.add(connection)
    connection.refresh_token_encrypted = encrypt(credentials.refresh_token)
    connection.google_account_email = google_account_email
    db.commit()

    return RedirectResponse(f"{settings.frontend_url}/dashboard/seo?google=connected")


@router.get("/status")
def get_status(
    business: Business = Depends(get_current_business),
    db: Session = Depends(get_db),
):
    connection = db.query(SeoGoogleConnection).filter(SeoGoogleConnection.business_id == business.id).first()
    if connection is None:
        return {"connected": False}
    return {
        "connected": True,
        "google_account_email": connection.google_account_email,
        "analytics_property_id": connection.analytics_property_id,
        "search_console_site_url": connection.search_console_site_url,
        "connected_at": connection.connected_at,
    }


class SeoGoogleConfigUpdate(BaseModel):
    # Both optional/independent -- a business might only want Search
    # Console, or only GA, or both. None (the field omitted or explicitly
    # null) leaves that one alone rather than clearing it; use an empty
    # string to explicitly clear one.
    analytics_property_id: Optional[str] = None
    search_console_site_url: Optional[str] = None


@router.patch("/config")
def update_config(
    body: SeoGoogleConfigUpdate,
    business: Business = Depends(get_current_business),
    db: Session = Depends(get_db),
):
    """Picks which GA4 property / Search Console site to read from --
    see SeoGoogleConnection's own docstring for why this can't be inferred
    automatically. 404 if Google isn't connected yet at all (nothing to
    configure)."""
    connection = db.query(SeoGoogleConnection).filter(SeoGoogleConnection.business_id == business.id).first()
    if connection is None:
        raise HTTPException(status_code=404, detail="Connect Google first (GET /authorize).")

    if body.analytics_property_id is not None:
        connection.analytics_property_id = body.analytics_property_id or None
    if body.search_console_site_url is not None:
        connection.search_console_site_url = body.search_console_site_url or None
    db.commit()

    return {
        "connected": True,
        "analytics_property_id": connection.analytics_property_id,
        "search_console_site_url": connection.search_console_site_url,
    }


@router.delete("")
def disconnect(
    business: Business = Depends(get_current_business),
    db: Session = Depends(get_db),
):
    db.query(SeoGoogleConnection).filter(SeoGoogleConnection.business_id == business.id).delete()
    db.commit()
    return {"connected": False}
