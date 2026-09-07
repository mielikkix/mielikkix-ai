"""app/integrations/email_marketing_providers/ -- the ABC + factory the
Email Marketing Agent is meant to depend on instead of raw Mailchimp HTTP
calls. Mocked at the MailchimpClient boundary (see test_mailchimp_client.py
for that client's own tests) -- this file is about the factory/adapter
wiring, not about Mailchimp's wire format.
"""

from unittest.mock import AsyncMock

import pytest

from app.core.encryption import encrypt
from app.integrations.email_marketing_providers import get_email_marketing_provider
from app.integrations.email_marketing_providers.mailchimp_provider import MailchimpEmailProvider
from app.models.mailchimp_connection import MailchimpConnection


def test_unrecognized_provider_returns_none():
    assert get_email_marketing_provider("carrier-pigeon") is None


def test_mailchimp_without_db_or_business_id_returns_none():
    assert get_email_marketing_provider("mailchimp") is None


def test_resend_raises_not_implemented():
    with pytest.raises(NotImplementedError):
        get_email_marketing_provider("resend")


def test_mailchimp_returns_none_when_business_has_no_connection(db_session, business):
    provider = get_email_marketing_provider("mailchimp", db_session, business["business_id"])

    assert provider is None


def test_mailchimp_returns_real_provider_when_connection_exists(db_session, business):
    connection = MailchimpConnection(
        business_id=business["business_id"],
        access_token_encrypted=encrypt("real-token"),
        server_prefix="us21",
        account_name="Acme Inc",
        login_email="owner@acme.com",
    )
    db_session.add(connection)
    db_session.commit()

    provider = get_email_marketing_provider("mailchimp", db_session, business["business_id"])

    assert isinstance(provider, MailchimpEmailProvider)


@pytest.mark.asyncio
async def test_provider_get_account_info_returns_best_effort_fields(db_session, business):
    connection = MailchimpConnection(
        business_id=business["business_id"], access_token_encrypted=encrypt("tok"), server_prefix="us21",
        account_name="Acme Inc", login_email="owner@acme.com",
    )
    db_session.add(connection)
    db_session.commit()
    provider = get_email_marketing_provider("mailchimp", db_session, business["business_id"])

    info = await provider.get_account_info()

    assert info.account_name == "Acme Inc"
    assert info.login_email == "owner@acme.com"


@pytest.mark.asyncio
async def test_provider_list_audiences_delegates_to_client(db_session, business, monkeypatch):
    connection = MailchimpConnection(
        business_id=business["business_id"], access_token_encrypted=encrypt("tok"), server_prefix="us21"
    )
    db_session.add(connection)
    db_session.commit()
    provider = get_email_marketing_provider("mailchimp", db_session, business["business_id"])
    monkeypatch.setattr(
        provider._client, "list_audiences", AsyncMock(return_value=[{"id": "l1", "name": "News", "member_count": 5}])
    )

    audiences = await provider.list_audiences()

    assert len(audiences) == 1
    assert audiences[0].id == "l1"
    assert audiences[0].name == "News"
    assert audiences[0].member_count == 5


@pytest.mark.asyncio
async def test_provider_wraps_client_errors_as_provider_error(db_session, business, monkeypatch):
    from app.integrations.email_marketing_providers.base import EmailMarketingProviderError
    from app.integrations.mailchimp_client import MailchimpClientError

    connection = MailchimpConnection(
        business_id=business["business_id"], access_token_encrypted=encrypt("tok"), server_prefix="us21"
    )
    db_session.add(connection)
    db_session.commit()
    provider = get_email_marketing_provider("mailchimp", db_session, business["business_id"])
    monkeypatch.setattr(
        provider._client, "list_audiences", AsyncMock(side_effect=MailchimpClientError("boom"))
    )

    with pytest.raises(EmailMarketingProviderError):
        await provider.list_audiences()
