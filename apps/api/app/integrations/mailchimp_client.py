"""Mailchimp OAuth2 + Marketing API v3 client for the per-tenant Email
Marketing Agent connection (app/api/mailchimp_oauth.py). NOT the same thing
as app/services/mailchimp_service.py -- that module talks to Mielikkix's
OWN single Mailchimp account via a static API key for the marketing site's
lead sync; this module is the real per-tenant OAuth client used to connect
a CUSTOMER's own Mailchimp account. The two never share code or state.

Everything here is verified against Mailchimp's own OAuth guide
(https://mailchimp.com/developer/marketing/guides/access-user-data-oauth-2/),
not assumed from Google's OAuth shape:

  - The authorization endpoint is login.mailchimp.com, not the API host.
  - Token exchange returns ONLY an access_token -- Mailchimp Marketing
    access tokens do not expire, so there is no refresh_token and nothing
    to refresh (unlike Google's Calendar/Reviews connections).
  - Before any Marketing API call can be made, the access token has to be
    exchanged once more at GET https://login.mailchimp.com/oauth2/metadata
    to learn `dc` (the account's data-center/server prefix, e.g. "us21")
    -- every Marketing API host is https://{dc}.api.mailchimp.com, unique
    per account, unlike Google's single fixed API host.
  - Marketing API calls made with an OAuth access token use the header
    `Authorization: OAuth {access_token}` -- NOT `Bearer`. (Confirmed by
    Mailchimp's own guide; this is genuinely different from the Bearer
    convention most other OAuth APIs use, so it is called out explicitly
    here rather than assumed.)

Mailchimp's metadata response only *guarantees* `dc` per their own
documentation -- `login`/`accountname`/`api_endpoint` are commonly present
but not part of the documented contract, so they are read defensively
(`.get()`, never assumed) and the API base URL is always built from `dc`
directly rather than trusted from an `api_endpoint` field.
"""

import logging

import httpx

logger = logging.getLogger(__name__)

_REQUEST_TIMEOUT_SECONDS = 10

MAILCHIMP_AUTHORIZE_URL = "https://login.mailchimp.com/oauth2/authorize"
MAILCHIMP_TOKEN_URL = "https://login.mailchimp.com/oauth2/token"
MAILCHIMP_METADATA_URL = "https://login.mailchimp.com/oauth2/metadata"


class MailchimpClientError(Exception):
    """Raised for any Mailchimp OAuth/API failure (bad code, expired
    token, network error, non-2xx response). Never carries anything that
    could leak the access token or client secret -- see _raise_for_response."""


def _raise_for_response(response: httpx.Response, action: str) -> None:
    if response.status_code >= 400:
        # Safe to log: Mailchimp's error body is validation/auth error text,
        # never an echo of the Authorization header or the token itself.
        logger.warning(
            "Mailchimp %s failed: status=%s body=%s",
            action, response.status_code, response.text[:500],
        )
        raise MailchimpClientError(f"Mailchimp API error during {action}: HTTP {response.status_code}")


async def exchange_code_for_token(client_id: str, client_secret: str, redirect_uri: str, code: str) -> str:
    """POST to the token endpoint (form-encoded, per Mailchimp's OAuth
    guide -- not JSON). Returns the access_token. Mailchimp's response
    shape is `{"access_token": "...", "expires_in": 0, "scope": null}`;
    `expires_in: 0` is Mailchimp's own documented way of saying the token
    does not expire, not an error."""
    payload = {
        "grant_type": "authorization_code",
        "client_id": client_id,
        "client_secret": client_secret,
        "redirect_uri": redirect_uri,
        "code": code,
    }
    async with httpx.AsyncClient(timeout=_REQUEST_TIMEOUT_SECONDS) as client:
        try:
            response = await client.post(MAILCHIMP_TOKEN_URL, data=payload)
        except httpx.RequestError as exc:
            raise MailchimpClientError(f"Mailchimp token exchange request failed: {exc.__class__.__name__}") from exc

    _raise_for_response(response, "token exchange")
    access_token = response.json().get("access_token")
    if not access_token:
        raise MailchimpClientError("Mailchimp token exchange succeeded but returned no access_token")
    return access_token


async def fetch_metadata(access_token: str) -> dict:
    """GET the metadata endpoint to learn `dc` (required) and whatever
    best-effort account info Mailchimp includes alongside it. Returns the
    raw dict; callers read `dc` directly and treat everything else as
    optional (see this module's own docstring)."""
    headers = {"Authorization": f"OAuth {access_token}"}
    async with httpx.AsyncClient(timeout=_REQUEST_TIMEOUT_SECONDS) as client:
        try:
            response = await client.get(MAILCHIMP_METADATA_URL, headers=headers)
        except httpx.RequestError as exc:
            raise MailchimpClientError(f"Mailchimp metadata request failed: {exc.__class__.__name__}") from exc

    _raise_for_response(response, "metadata lookup")
    data = response.json()
    if not data.get("dc"):
        raise MailchimpClientError("Mailchimp metadata response did not include a data center (dc)")
    return data


class MailchimpClient:
    """Talks to one connected business's own Mailchimp account. Constructed
    fresh per request from that business's decrypted access_token +
    server_prefix (see mailchimp_oauth.py / email_marketing_providers/
    mailchimp_provider.py) -- never a shared/global instance, since every
    tenant has their own account and credentials."""

    def __init__(self, access_token: str, server_prefix: str):
        self.access_token = access_token
        self.server_prefix = server_prefix

    def _api_base(self) -> str:
        return f"https://{self.server_prefix}.api.mailchimp.com/3.0"

    def _headers(self) -> dict:
        # "OAuth", not "Bearer" -- see this module's own docstring.
        return {"Authorization": f"OAuth {self.access_token}"}

    async def list_audiences(self) -> list[dict]:
        """GET /lists -- every audience (Mailchimp's term: "list") this
        account has, with basic stats. count=1000 is Mailchimp's own
        documented max page size; a real Mailchimp account very rarely has
        anywhere near that many audiences, so a single page is enough for
        Phase 1's audience picker (no pagination UI needed for this)."""
        url = f"{self._api_base()}/lists"
        async with httpx.AsyncClient(timeout=_REQUEST_TIMEOUT_SECONDS) as client:
            try:
                response = await client.get(url, headers=self._headers(), params={"count": 1000})
            except httpx.RequestError as exc:
                raise MailchimpClientError(f"Mailchimp audience list request failed: {exc.__class__.__name__}") from exc

        _raise_for_response(response, "list audiences")
        data = response.json()
        return [
            {
                "id": item["id"],
                "name": item.get("name", "(untitled audience)"),
                "member_count": (item.get("stats") or {}).get("member_count", 0),
            }
            for item in data.get("lists", [])
        ]

    async def get_audience(self, audience_id: str) -> dict:
        """GET /lists/{id} -- one audience's current name + member count.
        Used to refresh the selected audience's contact count for display
        without re-listing every audience."""
        url = f"{self._api_base()}/lists/{audience_id}"
        async with httpx.AsyncClient(timeout=_REQUEST_TIMEOUT_SECONDS) as client:
            try:
                response = await client.get(url, headers=self._headers())
            except httpx.RequestError as exc:
                raise MailchimpClientError(f"Mailchimp audience lookup request failed: {exc.__class__.__name__}") from exc

        _raise_for_response(response, "get audience")
        data = response.json()
        return {
            "id": data["id"],
            "name": data.get("name", "(untitled audience)"),
            "member_count": (data.get("stats") or {}).get("member_count", 0),
        }
