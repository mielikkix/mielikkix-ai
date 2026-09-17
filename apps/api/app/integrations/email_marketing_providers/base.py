"""EmailMarketingProvider -- abstraction around a tenant's connected email
marketing account, so the Email Marketing Agent is never tightly coupled
to Mailchimp specifically. Same idiom this repo already uses three times:
app/rag/providers/ (LLM providers), app/integrations/calendar_provider.py
(calendar providers), and app/integrations/review_platforms/ (review
platforms) -- an ABC + a get_*_provider() factory. Mailchimp is the first
(and, for this phase, only) real implementation; Resend is the documented
future second provider (see this package's __init__.py) -- deliberately
NOT implemented yet.

Phase 1 scope was connecting an account and reading its audiences. Phase 2
(campaigns) added create_campaign/set_campaign_content/send_test_email/
send_campaign/schedule_campaign/get_campaign/get_campaign_report --
Mailchimp is the system of record for the campaign itself (drafts, sends,
and reports on it natively via its own Campaigns API); this app never
duplicates that with its own per-recipient send loop or delivery tracking.
See app/services/campaign_service.py for how these are actually used.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime
from typing import Optional


@dataclass
class EmailAccountInfo:
    """Best-effort identifying info for the connected account -- shown in
    the dashboard as "Connected as: ...". Fields may be None even for a
    successfully connected account (see mailchimp_client.py's own
    docstring on which Mailchimp metadata fields are actually guaranteed)."""

    account_name: Optional[str]
    login_email: Optional[str]


@dataclass
class EmailAudience:
    """One audience/list, generic across providers (Mailchimp calls this a
    "list"; other providers use other names) -- the Email Marketing Agent
    only ever needs id/name/member_count, regardless of which provider a
    given tenant connected."""

    id: str
    name: str
    member_count: int


@dataclass
class CampaignInfo:
    """A campaign's current state on the provider's own side -- generic
    across providers the same way EmailAudience is, but for now every
    field here mirrors Mailchimp's own vocabulary directly (see
    MailchimpClient.get_campaign's own docstring on `status`) rather than
    inventing a parallel one, since Mailchimp is the only real provider
    that exists today."""

    id: str
    status: str
    emails_sent: int
    send_time: Optional[str]
    archive_url: Optional[str]


@dataclass
class CampaignReport:
    """Aggregated send results for a campaign that has actually sent --
    read-only, computed by the provider itself (Mailchimp's own /reports
    endpoint), never by this app aggregating per-recipient rows (there are
    none to aggregate -- see this package's own Phase 2 note above)."""

    emails_sent: int
    opens_total: int
    unique_opens: int
    open_rate: float
    click_rate: float
    unsubscribed: int
    hard_bounces: int
    soft_bounces: int


class EmailMarketingProvider(ABC):
    @abstractmethod
    async def get_account_info(self) -> EmailAccountInfo:
        """Best-effort account identity for display. Must not raise just
        because some fields are unavailable -- return None fields instead
        (see EmailAccountInfo)."""

    @abstractmethod
    async def list_audiences(self) -> list[EmailAudience]:
        """Every audience this connected account has. An empty list is a
        normal, valid result (a real account with zero audiences yet) --
        callers must render that as a clean empty state, not an error."""

    @abstractmethod
    async def get_audience(self, audience_id: str) -> EmailAudience:
        """One audience's current name + member count, by id. Raises
        EmailMarketingProviderError if that id no longer exists on the
        connected account (e.g. deleted on the provider's own side after
        being selected here)."""

    @abstractmethod
    async def create_campaign(
        self, audience_id: str, subject: str, from_name: Optional[str] = None, reply_to: Optional[str] = None
    ) -> CampaignInfo:
        """Creates a new campaign on the provider, targeting audience_id.
        Content is set separately (see set_campaign_content) -- a
        freshly-created campaign has none yet. Returns the provider's own
        CampaignInfo so the caller can persist its id (needed for every
        later call on this campaign)."""

    @abstractmethod
    async def set_campaign_content(self, campaign_id: str, html: str) -> None:
        """Sets/replaces this campaign's HTML body. Callable again to
        edit a campaign's content before it sends."""

    @abstractmethod
    async def send_test_email(self, campaign_id: str, test_emails: list[str]) -> None:
        """Sends a real test message for this campaign to the given
        addresses -- lets a human review actual rendered content before
        approving/sending for real. Never counts as the real send."""

    @abstractmethod
    async def send_campaign(self, campaign_id: str) -> None:
        """The real, irreversible send -- immediately, to this campaign's
        full targeted audience. Only ever called after an explicit human
        approval (see campaign_service.py's own approve/send split)."""

    @abstractmethod
    async def schedule_campaign(self, campaign_id: str, schedule_time: datetime) -> None:
        """Schedules this campaign to send at a future time. Unlike a
        locally-scheduled job, the provider itself is what fires the send
        at that time -- no local scheduler/cron is required for this to
        actually happen."""

    @abstractmethod
    async def get_campaign(self, campaign_id: str) -> CampaignInfo:
        """This campaign's current state, read live from the provider --
        used to refresh a locally-cached Campaign.status (see
        campaign_service.py) without duplicating delivery tracking here."""

    @abstractmethod
    async def get_campaign_report(self, campaign_id: str) -> CampaignReport:
        """Aggregated send results, read live from the provider. Only
        meaningful once a campaign has actually sent -- raises
        EmailMarketingProviderError for one that hasn't (see
        MailchimpClient.get_campaign_report's own docstring)."""


class EmailMarketingProviderError(Exception):
    """Raised for any provider-level failure (auth, network, not found).
    Provider-specific exceptions (e.g. MailchimpClientError) are caught and
    re-raised as this at the provider-implementation boundary, so callers
    (mailchimp_oauth.py, campaign_service.py) only ever need to catch one
    exception type regardless of which provider is connected."""
