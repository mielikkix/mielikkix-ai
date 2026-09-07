"""EmailMarketingProvider -- abstraction around a tenant's connected email
marketing account, so the Email Marketing Agent is never tightly coupled
to Mailchimp specifically. Same idiom this repo already uses three times:
app/rag/providers/ (LLM providers), app/integrations/calendar_provider.py
(calendar providers), and app/integrations/review_platforms/ (review
platforms) -- an ABC + a get_*_provider() factory. Mailchimp is the first
(and, for this phase, only) real implementation; Resend is the documented
future second provider (see this package's __init__.py) -- deliberately
NOT implemented yet.

Phase 1 scope only: this ABC covers connecting an account and reading its
audiences. It deliberately does NOT define any campaign/send methods yet
-- adding abstract methods for behavior that doesn't exist yet would be
speculative, not abstraction. Extend this ABC when campaign functionality
is actually built, in a later phase.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass
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


class EmailMarketingProviderError(Exception):
    """Raised for any provider-level failure (auth, network, not found).
    Provider-specific exceptions (e.g. MailchimpClientError) are caught and
    re-raised as this at the provider-implementation boundary, so callers
    (mailchimp_oauth.py) only ever need to catch one exception type
    regardless of which provider is connected."""
