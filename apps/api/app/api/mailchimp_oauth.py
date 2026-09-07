"""Email Marketing Agent: real per-tenant Mailchimp OAuth.

Follows the same shape/reasoning as app/api/calendar_oauth.py and
app/api/review_oauth.py -- read either first if this is your first time in
any of the three. The state-signing/tenant-resolution/redirect conventions
are identical; the OAuth mechanics themselves are NOT copied from Google's
shape, because Mailchimp's OAuth is genuinely different (verified against
Mailchimp's own OAuth guide -- see app/integrations/mailchimp_client.py's
own docstring for the specifics):

  - No `google_auth_oauthlib`-style Flow object -- Mailchimp's authorize
    URL and token exchange are simple enough to build directly with httpx,
    and there is no equivalent library convention to reuse here.
  - No refresh token, because Mailchimp Marketing access tokens do not
    expire. Nothing to refresh, ever.
  - An extra step Google doesn't need: a metadata call right after token
    exchange to learn which data center the account lives on.
  - No per-tenant OAuth "scope" concept the way Google has -- Mailchimp's
    OAuth app is authorized for the account as a whole, not scoped API
    permissions passed in the authorize URL.

Routes mounted under /api/businesses/me/mailchimp (the same "always
resolves tenant from the session cookie" convention every other /me route
in this codebase uses) -- deliberately separate from
app/services/mailchimp_service.py / app/api/leads.py, which is Mielikkix's
OWN single-account lead sync and is completely untouched by this file.

Flow, end to end:
  1. GET /authorize -- business is logged into the dashboard, clicks
     "Connect Mailchimp". This builds a signed `state` and 302s the
     browser to Mailchimp's own authorize screen.
  2. The business owner signs in to THEIR OWN Mailchimp account and
     approves access (Mielikkix's own registered OAuth app is what's
     requesting it, but the resulting token belongs to the tenant).
  3. GET /callback -- Mailchimp redirects back here with a `code`. This
     verifies `state`, exchanges `code` for an access token, fetches
     metadata (data center), encrypts the token, and upserts
     MailchimpConnection for that business.
  4. Browser lands back on the dashboard's Email Marketing page
     (?mailchimp=connected or ?mailchimp=error).
  5. GET /audiences + POST /select-audience -- a separate step after
     connecting, since (unlike Calendar's "primary") there is no
     meaningful default audience to assume.
"""

import hashlib
import hmac
import logging
import time

import httpx
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import RedirectResponse
from pydantic import BaseModel
from sqlalchemy.orm import Session

from ..core.config import settings
from ..core.database import get_db
from ..core.dependencies import get_current_business, get_current_user
from ..core.encryption import decrypt, encrypt
from ..integrations.mailchimp_client import (
    MAILCHIMP_AUTHORIZE_URL,
    MailchimpClient,
    MailchimpClientError,
    exchange_code_for_token,
    fetch_metadata,
)
from ..models.business import Business
from ..models.mailchimp_connection import MailchimpConnection
from ..models.user import User
from ..services import plan_service

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/businesses/me/mailchimp", tags=["email-marketing-oauth"])

_REDIRECT_PATH = "/api/businesses/me/mailchimp/callback"
# Same TTL as calendar_oauth.py/review_oauth.py's own _STATE_TTL_SECONDS --
# long enough for a real human to click through Mailchimp's consent
# screen, short enough that a leaked/logged `state` isn't a standing
# forgery risk.
_STATE_TTL_SECONDS = 600


def _redirect_uri() -> str:
    return f"{settings.api_public_base_url}{_REDIRECT_PATH}"


def _sign_state(business_id: str) -> str:
    """Identical scheme to calendar_oauth._sign_state / review_oauth.
    _sign_state -- see either's own comment. Deliberately not shared code
    between the three modules, same reasoning review_oauth.py's own
    _sign_state gives: OAuth state-signing is exactly the kind of thing
    worth keeping trivially self-contained per integration."""
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


def _build_authorize_url(state: str) -> str:
    """Mailchimp's authorize URL is a plain query string, not a client
    library call (see this module's own docstring on why there's no Flow
    object here) -- httpx.QueryParams handles the encoding correctly."""
    params = httpx.QueryParams(
        {
            "response_type": "code",
            "client_id": settings.mailchimp_oauth_client_id,
            "redirect_uri": _redirect_uri(),
            "state": state,
        }
    )
    return f"{MAILCHIMP_AUTHORIZE_URL}?{params}"


@router.get("/authorize")
def authorize(
    current_user: User = Depends(get_current_user),
    business: Business = Depends(get_current_business),
):
    plan_service.require_feature(business, "email_marketing_enabled")

    if not (settings.mailchimp_oauth_client_id and settings.mailchimp_oauth_client_secret):
        raise HTTPException(
            status_code=503,
            detail="Mailchimp connection isn't configured on this server yet.",
        )

    return RedirectResponse(_build_authorize_url(_sign_state(str(business.id))))


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
    what proves which business this callback belongs to. Every failure
    path redirects back to the dashboard with a query flag rather than a
    raw HTTP error page, since this is where a real user's browser lands
    mid-flow. `error` covers Mailchimp's own "user denied authorization"
    redirect (Mailchimp appends ?error=access_denied in that case, same as
    Google does)."""
    error_redirect = f"{settings.frontend_url}/dashboard/email-marketing?mailchimp=error"

    if error or not code or not state:
        return RedirectResponse(error_redirect)

    try:
        business_id = _verify_state(state)
    except ValueError:
        return RedirectResponse(error_redirect)

    try:
        access_token = await exchange_code_for_token(
            client_id=settings.mailchimp_oauth_client_id,
            client_secret=settings.mailchimp_oauth_client_secret,
            redirect_uri=_redirect_uri(),
            code=code,
        )
    except MailchimpClientError:
        logger.exception("Mailchimp OAuth token exchange failed for business_id=%s", business_id)
        return RedirectResponse(error_redirect)

    try:
        metadata = await fetch_metadata(access_token)
    except MailchimpClientError:
        logger.exception("Mailchimp OAuth metadata lookup failed for business_id=%s", business_id)
        return RedirectResponse(error_redirect)

    # Only `dc` is a guaranteed field per Mailchimp's own OAuth guide (see
    # mailchimp_client.py's docstring) -- fetch_metadata() already raises
    # if it's missing, everything else here is read defensively.
    server_prefix = metadata["dc"]
    account_name = metadata.get("accountname")
    login_email = (metadata.get("login") or {}).get("email")

    connection = db.query(MailchimpConnection).filter(MailchimpConnection.business_id == business_id).first()
    if connection is None:
        connection = MailchimpConnection(business_id=business_id)
        db.add(connection)
    connection.access_token_encrypted = encrypt(access_token)
    connection.server_prefix = server_prefix
    connection.account_name = account_name
    connection.login_email = login_email
    db.commit()

    return RedirectResponse(f"{settings.frontend_url}/dashboard/email-marketing?mailchimp=connected")


@router.get("/status")
def get_status(
    business: Business = Depends(get_current_business),
    db: Session = Depends(get_db),
):
    configured = bool(settings.mailchimp_oauth_client_id and settings.mailchimp_oauth_client_secret)
    connection = db.query(MailchimpConnection).filter(MailchimpConnection.business_id == business.id).first()
    if connection is None:
        return {"connected": False, "configured": configured}
    return {
        "connected": True,
        "configured": configured,
        "account_name": connection.account_name,
        "login_email": connection.login_email,
        "audience_id": connection.audience_id,
        "audience_name": connection.audience_name,
        "connected_at": connection.connected_at,
    }


@router.get("/audiences")
async def list_audiences(
    business: Business = Depends(get_current_business),
    db: Session = Depends(get_db),
):
    """Live call to Mailchimp for this connection's audiences -- the
    dashboard's audience picker calls this both right after connecting and
    whenever the business wants to change their selection. 404s if there's
    no connection yet at all (nothing to list audiences for), distinct
    from an empty list (a real account with zero audiences, a normal state
    the frontend should render as a clean empty state, not an error)."""
    connection = db.query(MailchimpConnection).filter(MailchimpConnection.business_id == business.id).first()
    if connection is None:
        raise HTTPException(status_code=404, detail="No Mailchimp connection yet -- connect first.")

    client = MailchimpClient(access_token=decrypt(connection.access_token_encrypted), server_prefix=connection.server_prefix)
    try:
        audiences = await client.list_audiences()
    except MailchimpClientError as exc:
        raise HTTPException(status_code=502, detail="Couldn't reach Mailchimp -- please try again shortly.") from exc

    return [{"id": a["id"], "name": a["name"], "member_count": a["member_count"]} for a in audiences]


class _SelectAudienceRequest(BaseModel):
    audience_id: str
    name: str | None = None


@router.post("/select-audience")
def select_audience(
    body: _SelectAudienceRequest,
    business: Business = Depends(get_current_business),
    db: Session = Depends(get_db),
):
    """Persists the chosen audience against this business's connection.
    Callable again later to CHANGE the selection -- there is no separate
    "change audience" endpoint, this one just overwrites whatever was
    selected before, the same way review_oauth.py's own select-location
    works."""
    connection = db.query(MailchimpConnection).filter(MailchimpConnection.business_id == business.id).first()
    if connection is None:
        raise HTTPException(status_code=404, detail="No Mailchimp connection yet -- connect first.")

    connection.audience_id = body.audience_id
    connection.audience_name = body.name
    db.commit()
    return {"connected": True, "audience_id": connection.audience_id, "audience_name": connection.audience_name}


@router.delete("")
def disconnect(
    business: Business = Depends(get_current_business),
    db: Session = Depends(get_db),
):
    db.query(MailchimpConnection).filter(MailchimpConnection.business_id == business.id).delete()
    db.commit()
    return {"connected": False}
