"""MailchimpEmailProvider -- adapts mailchimp_client.MailchimpClient to the
EmailMarketingProvider ABC (base.py), the same shape google_platform.py
adapts GoogleReviewsClient to ReviewPlatform. Keeps every Mailchimp-specific
HTTP/field detail inside mailchimp_client.py; this file only translates
that client's raw dicts into the provider's generic dataclasses.
"""

from datetime import datetime

from ..mailchimp_client import MailchimpClient, MailchimpClientError
from .base import (
    CampaignInfo,
    CampaignReport,
    EmailAccountInfo,
    EmailAudience,
    EmailMarketingProvider,
    EmailMarketingProviderError,
)


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

    @staticmethod
    def _campaign_info(data: dict) -> CampaignInfo:
        return CampaignInfo(
            id=data["id"],
            status=data["status"],
            emails_sent=data["emails_sent"],
            send_time=data.get("send_time"),
            archive_url=data.get("archive_url"),
        )

    async def create_campaign(
        self, audience_id: str, subject: str, from_name: str | None = None, reply_to: str | None = None
    ) -> CampaignInfo:
        try:
            data = await self._client.create_campaign(audience_id, subject, from_name=from_name, reply_to=reply_to)
        except MailchimpClientError as exc:
            raise EmailMarketingProviderError(str(exc)) from exc
        return self._campaign_info(data)

    async def set_campaign_content(self, campaign_id: str, html: str) -> None:
        try:
            await self._client.set_campaign_content(campaign_id, html)
        except MailchimpClientError as exc:
            raise EmailMarketingProviderError(str(exc)) from exc

    async def send_test_email(self, campaign_id: str, test_emails: list[str]) -> None:
        try:
            await self._client.send_test_email(campaign_id, test_emails)
        except MailchimpClientError as exc:
            raise EmailMarketingProviderError(str(exc)) from exc

    async def send_campaign(self, campaign_id: str) -> None:
        try:
            await self._client.send_campaign(campaign_id)
        except MailchimpClientError as exc:
            raise EmailMarketingProviderError(str(exc)) from exc

    async def schedule_campaign(self, campaign_id: str, schedule_time: datetime) -> None:
        try:
            await self._client.schedule_campaign(campaign_id, schedule_time)
        except MailchimpClientError as exc:
            raise EmailMarketingProviderError(str(exc)) from exc

    async def get_campaign(self, campaign_id: str) -> CampaignInfo:
        try:
            data = await self._client.get_campaign(campaign_id)
        except MailchimpClientError as exc:
            raise EmailMarketingProviderError(str(exc)) from exc
        return self._campaign_info(data)

    async def get_campaign_report(self, campaign_id: str) -> CampaignReport:
        try:
            data = await self._client.get_campaign_report(campaign_id)
        except MailchimpClientError as exc:
            raise EmailMarketingProviderError(str(exc)) from exc
        return CampaignReport(**data)
