"""Review & Reputation Agent: real per-tenant Google Business Profile OAuth.

Mirrors app/api/calendar_oauth.py's own shape/reasoning almost exactly --
read that file's comments first if this is your first time in either. Two
real differences from Calendar's flow:

  1. Scope is business.manage (google_reviews_client.REVIEWS_SCOPES), not
     the two narrower Calendar scopes.
  2. Business Profile has no "primary"-equivalent default location the way
     Calendar does -- the callback fetches this login's own Business
     Profile accounts/locations, and if the connected account has more
     than one location, the connection is left in a "connected, needs a
     location" state (location_id null) until the business finishes a
     separate GET /locations + POST /select-location step. See
     models/review_connection.py's own comment on this state.

Routes mounted under /api/businesses/me/reviews (same "always resolves
tenant from the session cookie" convention every other /me route already
uses) -- deliberately separate from /api/agents/reviews/... (agents_reviews.py,
the per-review analyze/respond/approve/publish routes): this file is about
the CONNECTION itself, not about any individual review.

Real Business Profile access (Google's own separate API approval, a
verified listing) is still required before any of this actually works end
to end -- see apps/agents/review-reputation/CLAUDE.md "Integrations
needed". This file is the real, working OAuth code that's ready the
moment that access exists; it does not simulate or fake a successful
connection in the meantime.
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

from ..core.config import settings
from ..core.database import get_db
from ..core.dependencies import get_current_business, get_current_user
from ..core.encryption import decrypt, encrypt
from ..integrations.google_reviews_client import GoogleReviewsClient, GoogleReviewsError, REVIEWS_SCOPES
from ..models.business import Business
from ..models.review_connection import ReviewConnection
from ..models.user import User
from ..services import plan_service

logger = logging.getLogger(__name__)

# Same two environment-variable escape hatches calendar_oauth.py sets, for
# the same reasons -- see that module's own comments on each. Setting them
# again here (both idempotent via setdefault) means this file works
# correctly even if calendar_oauth.py's module never happened to import
# first in a given process.
os.environ.setdefault("OAUTHLIB_RELAX_TOKEN_SCOPE", "1")
if settings.debug:
    os.environ.setdefault("OAUTHLIB_INSECURE_TRANSPORT", "1")

router = APIRouter(prefix="/api/businesses/me/reviews", tags=["review-reputation-oauth"])

_REDIRECT_PATH = "/api/businesses/me/reviews/callback"
_STATE_TTL_SECONDS = 600
# Fetches the connected account's own email (for "Connected as: ..." in the
# dashboard) alongside the one Business Profile scope -- same reasoning as
# calendar_oauth.py's own _OAUTH_SCOPES.
_OAUTH_SCOPES = REVIEWS_SCOPES + ["https://www.googleapis.com/auth/userinfo.email"]


def _redirect_uri() -> str:
    return f"{settings.api_public_base_url}{_REDIRECT_PATH}"


def _sign_state(business_id: str) -> str:
    """Identical scheme to calendar_oauth._sign_state -- see that
    function's own comment. Deliberately not shared code between the two
    modules: each is a handful of lines, and OAuth state-signing is
    exactly the kind of thing worth keeping trivially self-contained per
    integration rather than introducing a shared helper for two callers."""
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
                "client_id": settings.google_reviews_oauth_client_id,
                "client_secret": settings.google_reviews_oauth_client_secret,
                "auth_uri": "https://accounts.google.com/o/oauth2/auth",
                "token_uri": "https://oauth2.googleapis.com/token",
                "redirect_uris": [redirect_uri],
            }
        },
        scopes=_OAUTH_SCOPES,
        redirect_uri=redirect_uri,
    )


def _fetch_google_account_email(credentials) -> str | None:
    """Best-effort only, identical reasoning to calendar_oauth.py's own
    _fetch_google_account_email -- a failure here must never block the
    connection itself."""
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
    plan_service.require_feature(business, "review_reputation_enabled")

    if not (settings.google_reviews_oauth_client_id and settings.google_reviews_oauth_client_secret):
        raise HTTPException(
            status_code=503,
            detail="Google Business Profile connection isn't configured on this server yet.",
        )

    flow = _build_flow()
    # access_type=offline + prompt=consent -- same reasoning as
    # calendar_oauth.py's own authorize(): without both, a reconnecting
    # business would silently get no refresh_token back at all.
    auth_url, _ = flow.authorization_url(
        access_type="offline",
        prompt="consent",
        state=_sign_state(str(business.id)),
    )
    return RedirectResponse(auth_url)


@router.get("/callback")
async def callback(
    request: Request,
    code: str | None = None,
    state: str | None = None,
    error: str | None = None,
    db: Session = Depends(get_db),
):
    """No auth dependency here on purpose -- same reasoning as
    calendar_oauth.py's own callback(): `state`, not the session cookie, is
    what proves which business this belongs to. Every failure path
    redirects back to the dashboard with a query flag rather than a raw
    HTTP error page, since this is where a real user's browser lands
    mid-flow.
    """
    error_redirect = f"{settings.frontend_url}/dashboard/reviews?google_reviews=error"

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
        logger.exception("Google Reviews OAuth token exchange failed for business_id=%s", business_id)
        return RedirectResponse(error_redirect)

    if not credentials.refresh_token:
        return RedirectResponse(error_redirect)

    google_account_email = _fetch_google_account_email(credentials)

    # Immediately look up which Business Profile account/location(s) this
    # login actually manages -- there's no "primary" default the way
    # Calendar has, so the connection can't be considered usable yet
    # without at least an account_id.
    client = GoogleReviewsClient(
        client_id=settings.google_reviews_oauth_client_id,
        client_secret=settings.google_reviews_oauth_client_secret,
        refresh_token=credentials.refresh_token,
    )
    try:
        accounts = await client.get_accounts()
    except GoogleReviewsError:
        logger.exception("Google Reviews account lookup failed for business_id=%s", business_id)
        return RedirectResponse(error_redirect)

    if not accounts:
        return RedirectResponse(error_redirect)

    # More than one Business Profile account under a single login is rare
    # in practice (this is per-LOGIN, not per-location -- most businesses
    # have one account with several locations under it). Picking the
    # first one is a deliberate, documented simplification for this first
    # functional slice ("don't overengineer" -- an account-picker step
    # would be the same shape as the location one below, added later if a
    # real business actually needs it).
    account = accounts[0]
    account_id = account["name"].split("/")[-1]

    try:
        locations = await client.get_locations(account["name"])
    except GoogleReviewsError:
        logger.exception("Google Reviews location lookup failed for business_id=%s", business_id)
        return RedirectResponse(error_redirect)

    connection = db.query(ReviewConnection).filter(ReviewConnection.business_id == business_id).first()
    if connection is None:
        connection = ReviewConnection(business_id=business_id)
        db.add(connection)
    connection.refresh_token_encrypted = encrypt(credentials.refresh_token)
    connection.account_id = account_id
    connection.google_account_email = google_account_email

    if len(locations) == 1:
        location = locations[0]
        connection.location_id = location["name"].split("/")[-1]
        connection.location_title = location.get("title")
        db.commit()
        return RedirectResponse(f"{settings.frontend_url}/dashboard/reviews?google_reviews=connected")

    # Zero locations, or more than one: leave location_id null (see
    # models/review_connection.py's own comment on this state) rather than
    # silently guessing which one the business meant -- the dashboard's
    # "choose your location" step (GET /locations + POST /select-location
    # below) handles both cases the same way.
    connection.location_id = None
    connection.location_title = None
    db.commit()
    return RedirectResponse(f"{settings.frontend_url}/dashboard/reviews?google_reviews=choose_location")


@router.get("/status")
def get_status(
    business: Business = Depends(get_current_business),
    db: Session = Depends(get_db),
):
    configured = bool(settings.google_reviews_oauth_client_id and settings.google_reviews_oauth_client_secret)
    connection = db.query(ReviewConnection).filter(ReviewConnection.business_id == business.id).first()
    if connection is None:
        return {"connected": False, "needs_location": False, "configured": configured}
    return {
        "connected": connection.location_id is not None,
        "needs_location": connection.location_id is None,
        "google_account_email": connection.google_account_email,
        "location_title": connection.location_title,
        "connected_at": connection.connected_at,
        "configured": configured,
    }


@router.get("/locations")
async def list_locations(
    business: Business = Depends(get_current_business),
    db: Session = Depends(get_db),
):
    """Only meaningful once a connection exists with an account_id already
    set (see callback()'s "zero or multiple locations" branch) -- the
    dashboard's "choose your location" step calls this to render the
    picker. 404s if there's no connection yet at all (nothing to choose a
    location for), distinct from an empty list (a real account with zero
    locations, which is itself an error state the frontend should show
    plainly rather than an empty picker)."""
    connection = db.query(ReviewConnection).filter(ReviewConnection.business_id == business.id).first()
    if connection is None:
        raise HTTPException(status_code=404, detail="No Google Business Profile connection yet -- connect first.")

    client = GoogleReviewsClient(
        client_id=settings.google_reviews_oauth_client_id,
        client_secret=settings.google_reviews_oauth_client_secret,
        refresh_token=decrypt(connection.refresh_token_encrypted),
    )
    try:
        locations = await client.get_locations(f"accounts/{connection.account_id}")
    except GoogleReviewsError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc

    return [
        {"location_id": loc["name"].split("/")[-1], "title": loc.get("title", "(untitled)")} for loc in locations
    ]


class _SelectLocationRequest(BaseModel):
    location_id: str
    title: str | None = None


@router.post("/select-location")
def select_location(
    body: _SelectLocationRequest,
    business: Business = Depends(get_current_business),
    db: Session = Depends(get_db),
):
    connection = db.query(ReviewConnection).filter(ReviewConnection.business_id == business.id).first()
    if connection is None:
        raise HTTPException(status_code=404, detail="No Google Business Profile connection yet -- connect first.")

    connection.location_id = body.location_id
    connection.location_title = body.title
    db.commit()
    return {"connected": True, "location_title": connection.location_title}


@router.delete("")
def disconnect(
    business: Business = Depends(get_current_business),
    db: Session = Depends(get_db),
):
    db.query(ReviewConnection).filter(ReviewConnection.business_id == business.id).delete()
    db.commit()
    return {"connected": False}
