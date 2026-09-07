"""MailchimpEmailProvider -- adapts mailchimp_client.MailchimpClient to the
EmailMarketingProvider ABC (base.py), the same shape google_platform.py
adapts GoogleReviewsClient to ReviewPlatform. Keeps every Mailchimp-specific
HTTP/field detail inside mailchimp_client.py; this file only translates
that client's raw dicts into the provider's generic dataclasses.
"""

from ..mailchimp_client import MailchimpClient, MailchimpClientError
from .base import EmailAccountInfo, EmailAudience, EmailMarketingProvider, EmailMarketingProviderError


class MailchimpEmailProvider(EmailMarketingProvider):
    def __init__(self, client: MailchimpClient, account_name: str | None = None, login_email: str | None = None):
        self._client = client
        # Account info is captured once at OAuth-connect time (see
        # mailchimp_oauth.py's callback) and passed in here rather than
        # re-fetched live -- Mailchimp's metadata endpoint is part of the
        # OAuth exchange, not a general-purpose "get account info" API call
        # this provider can repeat on demand.
        self._account_name = account_name
        self._login_email = login_email

    async def get_account_info(self) -> EmailAccountInfo:
        return EmailAccountInfo(account_name=self._account_name, login_email=self._login_email)

    async def list_audiences(self) -> list[EmailAudience]:
        try:
            audiences = await self._client.list_audiences()
        except MailchimpClientError as exc:
            raise EmailMarketingProviderError(str(exc)) from exc
        return [EmailAudience(id=a["id"], name=a["name"], member_count=a["member_count"]) for a in audiences]

    async def get_audience(self, audience_id: str) -> EmailAudience:
        try:
            audience = await self._client.get_audience(audience_id)
        except MailchimpClientError as exc:
            raise EmailMarketingProviderError(str(exc)) from exc
        return EmailAudience(id=audience["id"], name=audience["name"], member_count=audience["member_count"])
