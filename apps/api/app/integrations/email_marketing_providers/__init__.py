"""Factory for EmailMarketingProvider, mirroring app/rag/providers/
__init__.py's get_llm_provider() and app/integrations/review_platforms/
__init__.py's get_review_platform() -- same "ABC + factory" idiom, applied
to email marketing providers.

Mailchimp is the only real implementation today. "resend" is listed in the
roster (it is the documented next provider -- see apps/agents/
email-marketing/CLAUDE.md and the product decision that this abstraction
must not require a rebuild to add it) but is NOT implemented in this
phase: calling it raises NotImplementedError with an honest message,
exactly like review_platforms/__init__.py does for facebook/yelp/etc,
rather than silently returning something that pretends to work.
"""

from typing import Optional

from sqlalchemy.orm import Session

from .base import EmailAccountInfo, EmailAudience, EmailMarketingProvider, EmailMarketingProviderError

PROVIDER_NAMES = ["mailchimp", "resend"]

_NOT_YET_BUILT = {
    "resend": "Resend is the planned second Email Marketing provider (see apps/agents/email-marketing/CLAUDE.md) -- not built yet.",
}


def get_email_marketing_provider(
    provider: str, db: Optional[Session] = None, business_id: Optional[str] = None
) -> Optional[EmailMarketingProvider]:
    """Returns None for a provider name this function doesn't recognize at
    all. Raises NotImplementedError for a real, roadmapped provider that
    isn't built yet (see _NOT_YET_BUILT).

    For "mailchimp": requires `db` and `business_id` (unlike some other
    factories in this codebase, there is no "global demo" fallback here --
    a per-tenant MailchimpConnection is the only way this integration is
    ever meant to work, see the product decision in this feature's own
    design brief). Returns None if that business has no connection yet, or
    hasn't finished selecting an audience is NOT checked here -- that is a
    business-logic question for the caller (mailchimp_oauth.py), not this
    factory's job.
    """
    if provider == "mailchimp":
        if db is None or business_id is None:
            return None

        from ...core.encryption import decrypt
        from ...models.mailchimp_connection import MailchimpConnection
        from ..mailchimp_client import MailchimpClient
        from .mailchimp_provider import MailchimpEmailProvider

        connection = db.query(MailchimpConnection).filter(MailchimpConnection.business_id == business_id).first()
        if connection is None:
            return None

        client = MailchimpClient(
            access_token=decrypt(connection.access_token_encrypted),
            server_prefix=connection.server_prefix,
        )
        return MailchimpEmailProvider(
            client, account_name=connection.account_name, login_email=connection.login_email
        )

    if provider in _NOT_YET_BUILT:
        raise NotImplementedError(_NOT_YET_BUILT[provider])

    return None


__all__ = [
    "EmailAccountInfo",
    "EmailAudience",
    "EmailMarketingProvider",
    "EmailMarketingProviderError",
    "PROVIDER_NAMES",
    "get_email_marketing_provider",
]
