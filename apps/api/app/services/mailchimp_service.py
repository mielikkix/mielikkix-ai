"""
Mailchimp Marketing API client for Mielikkix's OWN marketing/lead-gen
audience (account post@mielikkix.no) -- per root CLAUDE.md convention #6,
third-party integrations sit behind a dedicated service, not spread
through the app, the same shape as app/integrations/calendar_provider.py
and app/integrations/review_platforms/.

This is intentionally NOT a generic per-tenant Mailchimp integration --
connecting each Mielikkix CUSTOMER to their OWN Mailchimp account is
explicitly future work (see the Mailchimp implementation brief's "do not
implement yet" section). This module only ever talks to Mielikkix's one
existing Mailchimp account, for leads captured through the marketing
site's own "Book a Free Demo" form. WHICH leads that is (gated to one
business_id) is decided by app/services/lead_service.py, not here -- this
module just wraps the raw API.
"""

import hashlib
import logging
from dataclasses import dataclass

import httpx

from ..core.config import settings

logger = logging.getLogger(__name__)

_REQUEST_TIMEOUT_SECONDS = 10


class MailchimpError(Exception):
    """Raised for any Mailchimp API failure (auth, validation, network) or
    missing configuration. Callers (lead_service.py) catch this and leave
    mailchimp_synced=False rather than letting it fail the lead submission
    -- see this integration's design brief: 'Mailchimp failure does not
    lose a lead.' Never carries the raw Mailchimp response body in a way
    that could reach an end-user; that detail is logged here, not raised."""


class MailchimpRateLimitError(MailchimpError):
    """HTTP 429 specifically. Callers must NOT retry synchronously within
    the same request (no infinite retry loop) -- a manual/admin retry
    exists instead (POST /api/leads/{id}/sync-mailchimp)."""


def is_configured() -> bool:
    return bool(
        settings.mailchimp_api_key
        and settings.mailchimp_server_prefix
        and settings.mailchimp_audience_id
    )


def _api_base() -> str:
    return f"https://{settings.mailchimp_server_prefix}.api.mailchimp.com/3.0"


def _auth() -> tuple[str, str]:
    # Mailchimp's API accepts HTTP Basic Auth with any non-empty username
    # and the API key as the password -- "anystring" is Mailchimp's own
    # documented convention, not a secret itself.
    return ("anystring", settings.mailchimp_api_key)


def subscriber_hash(email: str) -> str:
    """Mailchimp's own addressing scheme for a list member: MD5 of the
    LOWERCASED email address, used as {subscriber_hash} in the
    /members/{subscriber_hash} URL. MD5 here is Mailchimp's API contract,
    not a security control -- this is not an endorsement of MD5 for
    anything security-sensitive elsewhere in this codebase."""
    return hashlib.md5(email.strip().lower().encode("utf-8")).hexdigest()


@dataclass
class MergeFields:
    first_name: str = ""
    last_name: str = ""
    company: str = ""
    phone: str = ""
    industry: str = ""
    interest: str = ""

    def to_payload(self) -> dict:
        # FNAME/LNAME are Mailchimp's own built-in merge tags on every
        # audience; COMPANY/PHONE/INDUSTRY/INTEREST must be created
        # manually first (see files/MAILCHIMP_SETUP.md) or Mailchimp
        # rejects the request with an "Invalid Resource" error for the
        # unrecognized tag. Empty values are omitted so submitting a lead
        # with, say, no phone number doesn't blank out a phone number a
        # human already entered by hand for that contact inside Mailchimp.
        fields = {
            "FNAME": self.first_name,
            "LNAME": self.last_name,
            "COMPANY": self.company,
            "PHONE": self.phone,
            "INDUSTRY": self.industry,
            "INTEREST": self.interest,
        }
        return {tag: value for tag, value in fields.items() if value}


def _raise_for_response(response: httpx.Response, action: str) -> None:
    if response.status_code == 429:
        raise MailchimpRateLimitError(f"Mailchimp rate limit hit (429) during {action}")
    if response.status_code >= 400:
        # Safe to log: Mailchimp's error body is validation/auth error text
        # (e.g. "Invalid Resource", "API Key Invalid"), never an echo of
        # the Authorization header or the API key itself. Never returned
        # to the end-user -- see lead_service.py.
        logger.warning(
            "Mailchimp %s failed: status=%s body=%s",
            action, response.status_code, response.text[:500],
        )
        raise MailchimpError(f"Mailchimp API error during {action}: HTTP {response.status_code}")


async def add_or_update_contact(email: str, merge_fields: MergeFields, marketing_consent: bool) -> str:
    """PUT /lists/{audience_id}/members/{subscriber_hash} -- creates the
    contact if it doesn't already exist, updates it otherwise (Mailchimp's
    own "add or update" semantics for this endpoint). Returns the
    Mailchimp contact id.

    marketing_consent controls `status_if_new` ONLY -- this payload never
    sets the plain `status` field, and that omission is load-bearing, not
    an oversight: `status_if_new` is only ever consulted by Mailchimp when
    it is creating a brand-new member, so an EXISTING contact's real
    status is always left completely alone by this call, regardless of
    marketing_consent. Re-submitting the demo form must never silently
    flip a real subscriber back to unsubscribed, and -- critically --
    must never silently RE-subscribe someone who explicitly unsubscribed
    themselves through Mailchimp's own unsubscribe link since their last
    visit, even if they tick the consent box again later. A genuine
    resubscribe has to go through Mailchimp's own re-permission flow, not
    this API call.

    For a genuinely NEW, consenting contact: `status_if_new` is
    "pending", not "subscribed". Setting "subscribed" directly from the
    API always bypasses the audience's configured Double Opt-In -- Mailchimp
    only sends its own confirmation/opt-in email when a new member's status
    is "pending". This module deliberately never manufactures its own
    confirmation flow (see this integration's add-on brief §5-6): Mailchimp
    owns sending and tracking that confirmation, and moves the contact to
    "subscribed" itself once the visitor clicks confirm. A non-consenting
    new contact still becomes "transactional" (Mailchimp's status for a
    contact it knows about -- e.g. to fulfil the demo request -- but must
    never send marketing campaigns to).
    """
    if not is_configured():
        raise MailchimpError("Mailchimp is not configured (MAILCHIMP_API_KEY/SERVER_PREFIX/AUDIENCE_ID)")

    url = f"{_api_base()}/lists/{settings.mailchimp_audience_id}/members/{subscriber_hash(email)}"
    payload = {
        "email_address": email.strip().lower(),
        "status_if_new": "pending" if marketing_consent else "transactional",
        "merge_fields": merge_fields.to_payload(),
    }

    async with httpx.AsyncClient(timeout=_REQUEST_TIMEOUT_SECONDS) as client:
        try:
            response = await client.put(url, json=payload, auth=_auth())
        except httpx.RequestError as exc:
            raise MailchimpError(f"Mailchimp request failed: {exc.__class__.__name__}") from exc

    _raise_for_response(response, "add_or_update_contact")
    return response.json()["id"]


async def add_tags_to_contact(email: str, tags: list[str]) -> None:
    """POST /lists/{audience_id}/members/{subscriber_hash}/tags -- Mailchimp
    treats re-adding an already-"active" tag as a no-op on its side, so no
    local de-duplication is needed here."""
    if not tags:
        return
    if not is_configured():
        raise MailchimpError("Mailchimp is not configured (MAILCHIMP_API_KEY/SERVER_PREFIX/AUDIENCE_ID)")

    url = f"{_api_base()}/lists/{settings.mailchimp_audience_id}/members/{subscriber_hash(email)}/tags"
    payload = {"tags": [{"name": tag, "status": "active"} for tag in tags]}

    async with httpx.AsyncClient(timeout=_REQUEST_TIMEOUT_SECONDS) as client:
        try:
            response = await client.post(url, json=payload, auth=_auth())
        except httpx.RequestError as exc:
            raise MailchimpError(f"Mailchimp request failed: {exc.__class__.__name__}") from exc

    _raise_for_response(response, "add_tags_to_contact")
