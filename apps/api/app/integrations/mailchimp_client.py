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
from datetime import datetime, timezone
from typing import Optional

import httpx
from ..core.log_redaction import redact

logger = logging.getLogger(__name__)

_REQUEST_TIMEOUT_SECONDS = 10

MAILCHIMP_AUTHORIZE_URL = "https://login.mailchimp.com/oauth2/authorize"
MAILCHIMP_TOKEN_URL = "https://login.mailchimp.com/oauth2/token"
MAILCHIMP_METADATA_URL = "https://login.mailchimp.com/oauth2/metadata"

# Mailchimp requires every campaign to carry a working unsubscribe link --
# verified against their own help docs (https://mailchimp.com/help/the-
# unsubscribe-merge-tag/): "*|UNSUB|*" is the documented merge tag, and
# Mailchimp only auto-adds its own footer with one if the content doesn't
# already include a link of some kind. Content set through set_campaign_
# content() that has no unsubscribe link of its own gets this tag appended
# automatically (see that method) rather than letting Mailchimp's send
# validation reject it later with "does not have a link to unsubscribe".
UNSUBSCRIBE_MERGE_TAG = "*|UNSUB|*"


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
            action, response.status_code, redact(response.text[:500]),
        )
        raise MailchimpClientError(f"Mailchimp API error during {action}: HTTP {response.status_code}")


def _campaign_dict(data: dict) -> dict:
    """Shared normalization for any Mailchimp response that represents a
    Campaign object (create_campaign's response and get_campaign's are the
    same shape) -- read defensively (`.get()`, never assumed) the same way
    every other response in this module is, so a caller (email_marketing_
    providers/mailchimp_provider.py's _campaign_info) can rely on `id`/
    `status`/`emails_sent` always being present regardless of which of
    these two calls produced the raw dict."""
    return {
        "id": data["id"],
        "status": data.get("status"),
        "emails_sent": data.get("emails_sent", 0),
        "send_time": data.get("send_time"),
        "archive_url": data.get("archive_url"),
    }


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
            logger.debug("Mailchimp token exchange starting: redirect_uri=%s", redirect_uri)
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

    # --- Campaigns (Mailchimp is the system of record for the campaign
    # itself here -- it drafts, sends, and reports on it natively; this
    # app never re-sends per-recipient itself). Endpoint paths/fields below
    # verified against Mailchimp's own Marketing API docs (mailchimp.com/
    # developer/marketing/api/campaigns/, /campaign-content/, /reports/),
    # not assumed. ------------------------------------------------------

    async def create_campaign(
        self,
        audience_id: str,
        subject: str,
        from_name: Optional[str] = None,
        reply_to: Optional[str] = None,
    ) -> dict:
        """POST /campaigns -- creates a "regular" campaign targeting this
        audience (Mailchimp's own term for a one-off, non-A/B, non-RSS
        campaign). Content is set separately (see set_campaign_content) --
        Mailchimp's API splits a campaign's metadata/settings from its
        HTML/plain-text body into two calls, a brand-new campaign always
        starts with none. Returns the same normalized dict shape get_
        campaign() does (see _campaign_dict) -- callers read `id` (needed
        for every subsequent call) and `status` (always "save" immediately
        after creation).

        IMPORTANT, verified against Mailchimp's actual settings schema and
        multiple real request examples (no `from_email` field exists in
        `settings` at all): there is no way to set the sending FROM email
        address per campaign through this API. Mailchimp always sends
        from the connected audience's own "Campaign Defaults" from_email
        (configured inside Mailchimp itself, tied to a domain that
        account has verified) -- `from_name` and `reply_to` are the only
        sender-identity fields this call can actually override. A
        business's chosen display from_email (this app's own Campaign.
        from_email field) is stored for reference only; it is never sent
        to Mailchimp, and never overrides the audience's real sending
        address."""
        url = f"{self._api_base()}/campaigns"
        settings: dict = {"subject_line": subject, "title": subject}
        if from_name:
            settings["from_name"] = from_name
        if reply_to:
            settings["reply_to"] = reply_to
        payload = {"type": "regular", "recipients": {"list_id": audience_id}, "settings": settings}

        async with httpx.AsyncClient(timeout=_REQUEST_TIMEOUT_SECONDS) as client:
            try:
                response = await client.post(url, headers=self._headers(), json=payload)
            except httpx.RequestError as exc:
                raise MailchimpClientError(f"Mailchimp create campaign request failed: {exc.__class__.__name__}") from exc

        _raise_for_response(response, "create campaign")
        return _campaign_dict(response.json())

    async def set_campaign_content(self, campaign_id: str, html: str) -> dict:
        """PUT /campaigns/{campaign_id}/content -- sets the campaign's HTML
        body. If the given HTML doesn't already reference the required
        unsubscribe merge tag (see UNSUBSCRIBE_MERGE_TAG above), a minimal
        footer containing it is appended automatically -- Mailchimp
        rejects a send later with "does not have a link to unsubscribe"
        otherwise, and failing that validation only at send time (after a
        human already approved this campaign) would be a worse experience
        than always ensuring it's present here."""
        body = html
        if UNSUBSCRIBE_MERGE_TAG not in html:
            body = (
                f"{html}\n"
                f'<p style="font-size:11px;color:#888;text-align:center;">'
                f'<a href="{UNSUBSCRIBE_MERGE_TAG}">Unsubscribe</a></p>'
            )
        url = f"{self._api_base()}/campaigns/{campaign_id}/content"
        async with httpx.AsyncClient(timeout=_REQUEST_TIMEOUT_SECONDS) as client:
            try:
                response = await client.put(url, headers=self._headers(), json={"html": body})
            except httpx.RequestError as exc:
                raise MailchimpClientError(f"Mailchimp set campaign content request failed: {exc.__class__.__name__}") from exc

        _raise_for_response(response, "set campaign content")
        return response.json()

    async def send_test_email(self, campaign_id: str, test_emails: list[str], send_type: str = "html") -> None:
        """POST /campaigns/{campaign_id}/actions/test -- send_type is
        "html" or "plaintext" (Mailchimp's own documented values)."""
        url = f"{self._api_base()}/campaigns/{campaign_id}/actions/test"
        payload = {"test_emails": test_emails, "send_type": send_type}
        async with httpx.AsyncClient(timeout=_REQUEST_TIMEOUT_SECONDS) as client:
            try:
                response = await client.post(url, headers=self._headers(), json=payload)
            except httpx.RequestError as exc:
                raise MailchimpClientError(f"Mailchimp send test email request failed: {exc.__class__.__name__}") from exc

        _raise_for_response(response, "send test email")

    async def send_campaign(self, campaign_id: str) -> None:
        """POST /campaigns/{campaign_id}/actions/send -- no request body.
        Sends immediately to the campaign's full audience; Mailchimp
        returns 204 on success. This is a real, irreversible send -- the
        caller (campaign_service.py) only ever reaches this after an
        explicit human approval."""
        url = f"{self._api_base()}/campaigns/{campaign_id}/actions/send"
        async with httpx.AsyncClient(timeout=_REQUEST_TIMEOUT_SECONDS) as client:
            try:
                response = await client.post(url, headers=self._headers())
            except httpx.RequestError as exc:
                raise MailchimpClientError(f"Mailchimp send campaign request failed: {exc.__class__.__name__}") from exc

        _raise_for_response(response, "send campaign")

    async def schedule_campaign(self, campaign_id: str, schedule_time: datetime) -> None:
        """POST /campaigns/{campaign_id}/actions/schedule -- schedule_time
        must be ISO 8601 UTC (verified against Mailchimp's own docs, e.g.
        "2026-04-01T14:00:00+00:00"). Unlike this app's abandoned Option B
        design, Mailchimp itself is what actually fires the send at that
        time -- no local scheduler/cron is needed for this to work."""
        url = f"{self._api_base()}/campaigns/{campaign_id}/actions/schedule"
        payload = {"schedule_time": schedule_time.astimezone(timezone.utc).isoformat()}
        async with httpx.AsyncClient(timeout=_REQUEST_TIMEOUT_SECONDS) as client:
            try:
                response = await client.post(url, headers=self._headers(), json=payload)
            except httpx.RequestError as exc:
                raise MailchimpClientError(f"Mailchimp schedule campaign request failed: {exc.__class__.__name__}") from exc

        _raise_for_response(response, "schedule campaign")

    async def get_campaign(self, campaign_id: str) -> dict:
        """GET /campaigns/{campaign_id} -- `status` is one of Mailchimp's
        own documented values: "save" | "paused" | "schedule" | "sending" |
        "sent" | "canceled" | "canceling" | "archived" (verified against
        Mailchimp's docs). campaign_service.py passes this straight
        through as this app's own Campaign.status once a campaign has
        actually been created in Mailchimp, rather than inventing a
        parallel status vocabulary that could drift from it."""
        url = f"{self._api_base()}/campaigns/{campaign_id}"
        async with httpx.AsyncClient(timeout=_REQUEST_TIMEOUT_SECONDS) as client:
            try:
                response = await client.get(url, headers=self._headers())
            except httpx.RequestError as exc:
                raise MailchimpClientError(f"Mailchimp get campaign request failed: {exc.__class__.__name__}") from exc

        _raise_for_response(response, "get campaign")
        return _campaign_dict(response.json())

    async def get_campaign_report(self, campaign_id: str) -> dict:
        """GET /reports/{campaign_id} -- only meaningful once a campaign
        has actually sent; Mailchimp 404s this for anything still in
        draft/scheduled, which surfaces here as a normal
        MailchimpClientError (callers should only call this once
        get_campaign's own status is "sending"/"sent"). Nested `opens`/
        `clicks`/`bounces` objects are read defensively (`.get()`,
        default 0/0.0) -- same "never assume a nested field beyond what's
        actually documented" discipline this module's own docstring
        already follows for the OAuth metadata response."""
        url = f"{self._api_base()}/reports/{campaign_id}"
        async with httpx.AsyncClient(timeout=_REQUEST_TIMEOUT_SECONDS) as client:
            try:
                response = await client.get(url, headers=self._headers())
            except httpx.RequestError as exc:
                raise MailchimpClientError(f"Mailchimp get campaign report request failed: {exc.__class__.__name__}") from exc

        _raise_for_response(response, "get campaign report")
        data = response.json()
        opens = data.get("opens") or {}
        clicks = data.get("clicks") or {}
        bounces = data.get("bounces") or {}
        return {
            "emails_sent": data.get("emails_sent", 0),
            "opens_total": opens.get("opens_total", 0),
            "unique_opens": opens.get("unique_opens", 0),
            "open_rate": opens.get("open_rate", 0.0),
            "click_rate": clicks.get("click_rate", 0.0),
            "unsubscribed": data.get("unsubscribed", 0),
            "hard_bounces": bounces.get("hard_bounces", 0),
            "soft_bounces": bounces.get("soft_bounces", 0),
        }
