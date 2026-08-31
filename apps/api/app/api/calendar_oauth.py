"""Booking Assistant Phase 5: real per-tenant Google Calendar OAuth.

Every route here is mounted under /api/businesses/me/calendar (the same
"always resolves tenant from the session cookie" convention every other
/me route in businesses.py already uses) but lives in its own file rather
than businesses.py itself, since the OAuth Authorization Code dance (sign,
redirect, verify, exchange) is a distinct enough concern to read on its
own.

Flow, end to end:
  1. GET /authorize -- business is logged into the dashboard, clicks
     "Connect Google Calendar". This builds a signed `state` and 302s the
     browser to Google's consent screen.
  2. The business owner signs in to THEIR OWN Google account and approves
     access to THEIR OWN calendar (this is the whole point -- Mielikkix's
     own OAuth client is the one making the request, but the consent and
     resulting token are the tenant's).
  3. GET /callback -- Google redirects back here with a `code`. This
     verifies `state`, exchanges `code` for tokens, encrypts the refresh
     token, and upserts CalendarConnection for that business.
  4. Browser lands back on the dashboard Settings page
     (?calendar=connected or ?calendar=error).

Uses google_auth_oauthlib.flow.Flow (the Web-application counterpart to
scripts/connect_google_calendar.py's InstalledAppFlow) since this needs a
real server-side redirect URI, not a local throwaway listener.
"""

import hashlib
import hmac
import logging
import os
import time

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import RedirectResponse
from google_auth_oauthlib.flow import Flow
from sqlalchemy.orm import Session

from ..core.config import settings
from ..core.database import get_db
from ..core.dependencies import get_current_business, get_current_user
from ..core.encryption import encrypt
from ..integrations.google_calendar_client import CALENDAR_SCOPES
from ..models.business import Business
from ..models.calendar_connection import CalendarConnection
from ..models.user import User
from ..services import plan_service

logger = logging.getLogger(__name__)

# Google silently adds "openid" and "email" to whatever scopes we request
# the moment userinfo.email is one of them (confirmed live: we ask for 3
# scopes, Google's redirect comes back listing 5) -- completely normal
# Google behavior, but oauthlib (which google-auth-oauthlib's Flow uses
# for the token exchange) treats any scope it didn't ask for as an error
# by default and raises, which silently became this route's generic
# "couldn't connect" failure. Safe in every environment, not just DEBUG --
# unlike the insecure-transport flag below, this has nothing to do with
# whether the connection is HTTP or HTTPS.
os.environ.setdefault("OAUTHLIB_RELAX_TOKEN_SCOPE", "1")

# oauthlib separately refuses to process ANY authorization response whose
# URL isn't https:// -- confirmed live (a real oauthlib.oauth2.rfc6749.
# errors.InsecureTransportError) the moment local dev's plain
# http://localhost:8000 callback URL reached Flow.fetch_token(). Gated on
# settings.debug specifically because this one actually does relax a real
# security check -- production's callback is real HTTPS (api.mielikkix.ai)
# and must keep oauthlib's default enforcement, only local dev needs the
# escape hatch.
if settings.debug:
    os.environ.setdefault("OAUTHLIB_INSECURE_TRANSPORT", "1")

router = APIRouter(prefix="/api/businesses/me/calendar", tags=["booking-assistant-oauth"])

_REDIRECT_PATH = "/api/businesses/me/calendar/callback"

# Fetches the connected account's own email (for "Connected as: ..." in
# Settings) alongside the two calendar scopes -- best-effort only, see
# _fetch_google_account_email below. Not added to CALENDAR_SCOPES itself
# (google_calendar_client.py) since the Desktop-app demo-calendar flow
# (scripts/connect_google_calendar.py) has no UI to show an email in and
# shouldn't ask for more access than it uses.
_OAUTH_SCOPES = CALENDAR_SCOPES + ["https://www.googleapis.com/auth/userinfo.email"]

# How long a signed `state` stays valid -- long enough for a real human to
# click through Google's consent screen, short enough that a leaked/logged
# `state` (e.g. in a proxy's access log) isn't a standing forgery risk.
_STATE_TTL_SECONDS = 600


def _redirect_uri() -> str:
    return f"{settings.api_public_base_url}{_REDIRECT_PATH}"


def _sign_state(business_id: str) -> str:
    """HMAC-signed `business_id:timestamp`, keyed by the same secret_key
    that already signs this app's auth JWTs (core/security.py) -- same
    "only this server could have produced this" guarantee, applied to an
    OAuth state param instead of a login token. stdlib hmac/hashlib, no new
    dependency (mirrors the reasoning in this codebase for reusing zoneinfo
    over adding a timezone library)."""
    payload = f"{business_id}:{int(time.time())}"
    signature = hmac.new(settings.secret_key.encode(), payload.encode(), hashlib.sha256).hexdigest()
    return f"{payload}:{signature}"


def _verify_state(state: str) -> str:
    """Returns the business_id encoded in `state` if its signature is valid
    and it hasn't expired; raises ValueError otherwise. `hmac.compare_digest`
    (constant-time) rather than `==`, same reason password/token comparisons
    elsewhere in this app avoid a plain equality check."""
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
                "client_id": settings.google_calendar_oauth_client_id,
                "client_secret": settings.google_calendar_oauth_client_secret,
                "auth_uri": "https://accounts.google.com/o/oauth2/auth",
                "token_uri": "https://oauth2.googleapis.com/token",
                "redirect_uris": [redirect_uri],
            }
        },
        scopes=_OAUTH_SCOPES,
        redirect_uri=redirect_uri,
    )


def _fetch_google_account_email(credentials) -> str | None:
    """Best-effort only -- a failure here (e.g. the userinfo scope wasn't
    actually granted for some reason) must never block the connection
    itself, since booking works fine with just the calendar scopes. Shown
    in Settings as "Connected as: ..." purely so the business owner can
    confirm they connected the right account."""
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
):
    plan_service.require_feature(business, "booking_enabled")

    if not (settings.google_calendar_oauth_client_id and settings.google_calendar_oauth_client_secret):
        raise HTTPException(
            status_code=503,
            detail="Calendar connection isn't configured on this server yet.",
        )

    flow = _build_flow()
    # access_type=offline: without this Google only ever hands back a
    # short-lived access token, no refresh token -- useless here since this
    # app needs to call the Calendar API long after the user's browser
    # session ended. prompt=consent: forces the consent screen (and a fresh
    # refresh token) every time, even for an account that already approved
    # this app once before -- otherwise a business reconnecting after a
    # revoke/disconnect would silently get no refresh_token back at all
    # (Google only issues one on the FIRST consent for a given account+app).
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
    """No auth dependency here on purpose: Google redirects the browser here
    directly (it isn't carrying this app's session cookie in a way we
    should rely on for tenant identity), so `state` -- not the session -- is
    what proves which business this callback belongs to. Every failure path
    redirects back to Settings with ?calendar=error rather than a raw HTTP
    error page, since this is where a real user's browser lands mid-flow.
    """
    error_redirect = f"{settings.frontend_url}/dashboard/settings?calendar=error"

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
        # Logged, not swallowed silently -- this is a real customer's
        # browser mid-flow, so it still gets the friendly ?calendar=error
        # redirect, but a bare "couldn't connect" with nothing in the logs
        # is nearly undebuggable (this is exactly how the
        # OAUTHLIB_RELAX_TOKEN_SCOPE issue above went unnoticed until
        # traced by hand from the access log).
        logger.exception("Google Calendar OAuth token exchange failed for business_id=%s", business_id)
        return RedirectResponse(error_redirect)

    if not credentials.refresh_token:
        return RedirectResponse(error_redirect)

    google_account_email = _fetch_google_account_email(credentials)

    connection = db.query(CalendarConnection).filter(CalendarConnection.business_id == business_id).first()
    if connection is None:
        connection = CalendarConnection(business_id=business_id)
        db.add(connection)
    connection.refresh_token_encrypted = encrypt(credentials.refresh_token)
    connection.calendar_id = "primary"
    connection.google_account_email = google_account_email
    db.commit()

    return RedirectResponse(f"{settings.frontend_url}/dashboard/settings?calendar=connected")


@router.get("/status")
def get_status(
    business: Business = Depends(get_current_business),
    db: Session = Depends(get_db),
):
    connection = db.query(CalendarConnection).filter(CalendarConnection.business_id == business.id).first()
    if connection is None:
        return {"connected": False}
    return {
        "connected": True,
        "calendar_id": connection.calendar_id,
        "google_account_email": connection.google_account_email,
        "connected_at": connection.connected_at,
    }


@router.delete("")
def disconnect(
    business: Business = Depends(get_current_business),
    db: Session = Depends(get_db),
):
    db.query(CalendarConnection).filter(CalendarConnection.business_id == business.id).delete()
    db.commit()
    return {"connected": False}
