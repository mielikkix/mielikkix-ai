"""app/services/campaign_service.py -- Option A campaign lifecycle (local
draft -> approve -> Mailchimp create/content/send/schedule -> status read
back from Mailchimp). Mocked at the MailchimpClient boundary, same
"construct a real MailchimpConnection + provider via the real factory,
monkeypatch MailchimpClient itself" idiom test_mailchimp_oauth.py's own
_patch_client helper uses -- so campaign_service's own calls to
get_email_marketing_provider() are exercised for real, only the actual
HTTP-calling client underneath is faked.
"""

from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.core.encryption import encrypt
from app.models.mailchimp_connection import MailchimpConnection
from app.services import campaign_service
from app.services.campaign_service import CampaignSendError


def _connect_mailchimp(db_session, business_id, audience_id="aud1", audience_name="Newsletter"):
    connection = MailchimpConnection(
        business_id=business_id,
        access_token_encrypted=encrypt("tok"),
        server_prefix="us21",
        audience_id=audience_id,
        audience_name=audience_name,
    )
    db_session.add(connection)
    db_session.commit()
    return connection


def _patch_client(monkeypatch, **method_returns):
    """Patches MailchimpClient at its defining module (app.integrations.
    mailchimp_client), not on campaign_service -- get_email_marketing_
    provider() imports MailchimpClient locally from its own module at call
    time (see that factory's own comment), same reasoning test_mailchimp_
    oauth.py's own _patch_client gives."""
    from app.integrations import mailchimp_client as mailchimp_client_module

    fake_client = MagicMock()
    fake_client.create_campaign = AsyncMock(
        return_value=method_returns.get(
            "create_campaign", {"id": "camp1", "status": "save", "emails_sent": 0, "send_time": None, "archive_url": None}
        )
    )
    fake_client.set_campaign_content = AsyncMock(return_value=method_returns.get("set_campaign_content", {}))
    fake_client.send_test_email = AsyncMock(return_value=method_returns.get("send_test_email", None))
    fake_client.send_campaign = AsyncMock(return_value=method_returns.get("send_campaign", None))
    fake_client.schedule_campaign = AsyncMock(return_value=method_returns.get("schedule_campaign", None))
    fake_client.get_campaign = AsyncMock(
        return_value=method_returns.get(
            "get_campaign", {"id": "camp1", "status": "sending", "emails_sent": 0, "send_time": None, "archive_url": None}
        )
    )
    fake_client.get_campaign_report = AsyncMock(
        return_value=method_returns.get(
            "get_campaign_report",
            {
                "emails_sent": 100, "opens_total": 40, "unique_opens": 30, "open_rate": 30.0,
                "click_rate": 5.0, "unsubscribed": 1, "hard_bounces": 0, "soft_bounces": 1,
            },
        )
    )
    monkeypatch.setattr(mailchimp_client_module, "MailchimpClient", MagicMock(return_value=fake_client))
    return fake_client


def _draft_campaign_kwargs():
    return dict(
        subject="Big Sale", from_name="Acme", from_email="hello@acme.com",
        reply_to="owner@acme.com", body_html="<p>Save big!</p>",
        mailchimp_audience_id="aud1", mailchimp_audience_name="Newsletter",
    )


# --- create_draft / update_draft / list / get ----------------------------


def test_create_draft_starts_in_draft_status(db_session, business):
    campaign = campaign_service.create_draft(db_session, business["business_id"], subject="Hello")

    assert campaign.status == "draft"
    assert campaign.subject == "Hello"
    assert campaign.mailchimp_campaign_id is None


def test_update_draft_only_allowed_while_draft(db_session, business):
    campaign = campaign_service.create_draft(db_session, business["business_id"], subject="Hello")
    campaign.status = "approved"
    db_session.commit()

    with pytest.raises(ValueError):
        campaign_service.update_draft(db_session, business["business_id"], str(campaign.id), subject="Changed")


def test_update_draft_ignores_unknown_fields(db_session, business):
    campaign = campaign_service.create_draft(db_session, business["business_id"], subject="Hello")

    updated = campaign_service.update_draft(db_session, business["business_id"], str(campaign.id), subject="New", not_a_real_field="x")

    assert updated.subject == "New"


def test_get_campaign_not_found_raises(db_session, business):
    with pytest.raises(ValueError):
        campaign_service.get_campaign(db_session, business["business_id"], "00000000-0000-0000-0000-000000000000")


def test_list_campaigns_filters_by_status(db_session, business):
    campaign_service.create_draft(db_session, business["business_id"], subject="A")
    b = campaign_service.create_draft(db_session, business["business_id"], subject="B")
    b.status = "approved"
    db_session.commit()

    drafts = campaign_service.list_campaigns(db_session, business["business_id"], status="draft")

    assert len(drafts) == 1
    assert drafts[0].subject == "A"


# --- approve_campaign ------------------------------------------------


def test_approve_campaign_requires_subject_body_reply_to_and_audience(db_session, business):
    campaign = campaign_service.create_draft(db_session, business["business_id"])

    with pytest.raises(ValueError, match="missing required"):
        campaign_service.approve_campaign(db_session, business["business_id"], str(campaign.id))


def test_approve_campaign_does_not_require_from_email(db_session, business):
    """from_email is display-only -- Mailchimp has no field for it (see
    mailchimp_client.create_campaign's own docstring) -- requiring it
    before approval would falsely imply it does something functional."""
    campaign = campaign_service.create_draft(
        db_session, business["business_id"],
        subject="Hi", body_html="<p>hi</p>", reply_to="owner@acme.com", mailchimp_audience_id="aud1",
    )

    approved = campaign_service.approve_campaign(db_session, business["business_id"], str(campaign.id))

    assert approved.status == "approved"


def test_approve_campaign_only_from_draft(db_session, business):
    campaign = campaign_service.create_draft(db_session, business["business_id"], **_draft_campaign_kwargs())
    campaign_service.approve_campaign(db_session, business["business_id"], str(campaign.id))

    with pytest.raises(ValueError):
        campaign_service.approve_campaign(db_session, business["business_id"], str(campaign.id))


# --- send_campaign -----------------------------------------------------


@pytest.mark.asyncio
async def test_send_campaign_requires_approved_or_later_status(db_session, business):
    campaign = campaign_service.create_draft(db_session, business["business_id"], **_draft_campaign_kwargs())

    with pytest.raises(ValueError):
        await campaign_service.send_campaign(db_session, business["business_id"], str(campaign.id))


@pytest.mark.asyncio
async def test_send_campaign_without_mailchimp_connection_raises_send_error(db_session, business):
    campaign = campaign_service.create_draft(db_session, business["business_id"], **_draft_campaign_kwargs())
    campaign_service.approve_campaign(db_session, business["business_id"], str(campaign.id))

    with pytest.raises(CampaignSendError):
        await campaign_service.send_campaign(db_session, business["business_id"], str(campaign.id))


@pytest.mark.asyncio
async def test_send_campaign_creates_sets_content_and_sends(db_session, business, monkeypatch):
    _connect_mailchimp(db_session, business["business_id"])
    fake_client = _patch_client(
        monkeypatch,
        get_campaign={"id": "camp1", "status": "sending", "emails_sent": 0, "send_time": "2026-04-01T14:00:00+00:00", "archive_url": None},
    )
    campaign = campaign_service.create_draft(db_session, business["business_id"], **_draft_campaign_kwargs())
    campaign_service.approve_campaign(db_session, business["business_id"], str(campaign.id))

    result = await campaign_service.send_campaign(db_session, business["business_id"], str(campaign.id))

    fake_client.create_campaign.assert_awaited_once()
    fake_client.set_campaign_content.assert_awaited_once_with("camp1", "<p>Save big!</p>")
    fake_client.send_campaign.assert_awaited_once_with("camp1")
    assert result.mailchimp_campaign_id == "camp1"
    assert result.status == "sending"
    assert result.sent_at is not None


@pytest.mark.asyncio
async def test_send_campaign_reuses_existing_mailchimp_campaign_id(db_session, business, monkeypatch):
    """A retry (e.g. after an earlier failed attempt, or after a test
    send already created the Mailchimp campaign) must not create a
    second, duplicate campaign on Mailchimp."""
    _connect_mailchimp(db_session, business["business_id"])
    fake_client = _patch_client(monkeypatch)
    campaign = campaign_service.create_draft(db_session, business["business_id"], **_draft_campaign_kwargs())
    campaign_service.approve_campaign(db_session, business["business_id"], str(campaign.id))
    campaign.mailchimp_campaign_id = "already-created"
    campaign.status = "save"
    db_session.commit()

    await campaign_service.send_campaign(db_session, business["business_id"], str(campaign.id))

    fake_client.create_campaign.assert_not_awaited()
    fake_client.set_campaign_content.assert_awaited_once_with("already-created", "<p>Save big!</p>")
    fake_client.send_campaign.assert_awaited_once_with("already-created")


@pytest.mark.asyncio
async def test_send_campaign_wraps_upstream_failure_as_campaign_send_error(db_session, business, monkeypatch):
    from app.integrations.mailchimp_client import MailchimpClientError

    _connect_mailchimp(db_session, business["business_id"])
    fake_client = _patch_client(monkeypatch)
    fake_client.send_campaign = AsyncMock(side_effect=MailchimpClientError("boom"))
    campaign = campaign_service.create_draft(db_session, business["business_id"], **_draft_campaign_kwargs())
    campaign_service.approve_campaign(db_session, business["business_id"], str(campaign.id))

    with pytest.raises(CampaignSendError):
        await campaign_service.send_campaign(db_session, business["business_id"], str(campaign.id))


# --- schedule_campaign ---------------------------------------------------


@pytest.mark.asyncio
async def test_schedule_campaign_rejects_a_past_time(db_session, business):
    _connect_mailchimp(db_session, business["business_id"])
    campaign = campaign_service.create_draft(db_session, business["business_id"], **_draft_campaign_kwargs())
    campaign_service.approve_campaign(db_session, business["business_id"], str(campaign.id))

    with pytest.raises(ValueError, match="future"):
        await campaign_service.schedule_campaign(
            db_session, business["business_id"], str(campaign.id), datetime.now(timezone.utc) - timedelta(hours=1)
        )


@pytest.mark.asyncio
async def test_schedule_campaign_success_updates_status_and_scheduled_at(db_session, business, monkeypatch):
    _connect_mailchimp(db_session, business["business_id"])
    fake_client = _patch_client(monkeypatch, get_campaign={"id": "camp1", "status": "schedule", "emails_sent": 0, "send_time": None, "archive_url": None})
    campaign = campaign_service.create_draft(db_session, business["business_id"], **_draft_campaign_kwargs())
    campaign_service.approve_campaign(db_session, business["business_id"], str(campaign.id))
    when = datetime.now(timezone.utc) + timedelta(days=1)

    result = await campaign_service.schedule_campaign(db_session, business["business_id"], str(campaign.id), when)

    fake_client.schedule_campaign.assert_awaited_once_with("camp1", when)
    assert result.status == "schedule"
    assert result.scheduled_at == when


# --- send_test_email -------------------------------------------------


@pytest.mark.asyncio
async def test_send_test_email_requires_approved_status(db_session, business):
    campaign = campaign_service.create_draft(db_session, business["business_id"], **_draft_campaign_kwargs())

    with pytest.raises(ValueError):
        await campaign_service.send_test_email(db_session, business["business_id"], str(campaign.id), ["a@example.com"])


@pytest.mark.asyncio
async def test_send_test_email_requires_at_least_one_address(db_session, business, monkeypatch):
    _connect_mailchimp(db_session, business["business_id"])
    _patch_client(monkeypatch)
    campaign = campaign_service.create_draft(db_session, business["business_id"], **_draft_campaign_kwargs())
    campaign_service.approve_campaign(db_session, business["business_id"], str(campaign.id))

    with pytest.raises(ValueError):
        await campaign_service.send_test_email(db_session, business["business_id"], str(campaign.id), [])


@pytest.mark.asyncio
async def test_send_test_email_creates_campaign_and_sends_test(db_session, business, monkeypatch):
    _connect_mailchimp(db_session, business["business_id"])
    fake_client = _patch_client(monkeypatch)
    campaign = campaign_service.create_draft(db_session, business["business_id"], **_draft_campaign_kwargs())
    campaign_service.approve_campaign(db_session, business["business_id"], str(campaign.id))

    result = await campaign_service.send_test_email(db_session, business["business_id"], str(campaign.id), ["me@example.com"])

    fake_client.create_campaign.assert_awaited_once()
    fake_client.send_test_email.assert_awaited_once_with("camp1", ["me@example.com"])
    # A test send must never move the campaign's own status.
    assert result.status == "approved"


# --- refresh_campaign_status / get_campaign_report ------------------------


@pytest.mark.asyncio
async def test_refresh_campaign_status_is_a_noop_without_a_mailchimp_campaign(db_session, business):
    campaign = campaign_service.create_draft(db_session, business["business_id"], **_draft_campaign_kwargs())

    result = await campaign_service.refresh_campaign_status(db_session, business["business_id"], str(campaign.id))

    assert result.status == "draft"


@pytest.mark.asyncio
async def test_refresh_campaign_status_updates_from_mailchimp(db_session, business, monkeypatch):
    _connect_mailchimp(db_session, business["business_id"])
    _patch_client(monkeypatch, get_campaign={"id": "camp1", "status": "sent", "emails_sent": 50, "send_time": "2026-04-01T14:00:00+00:00", "archive_url": None})
    campaign = campaign_service.create_draft(db_session, business["business_id"], **_draft_campaign_kwargs())
    campaign.mailchimp_campaign_id = "camp1"
    campaign.status = "sending"
    db_session.commit()

    result = await campaign_service.refresh_campaign_status(db_session, business["business_id"], str(campaign.id))

    assert result.status == "sent"
    assert result.sent_at is not None


@pytest.mark.asyncio
async def test_refresh_campaign_status_swallows_upstream_failure(db_session, business, monkeypatch):
    from app.integrations.mailchimp_client import MailchimpClientError

    _connect_mailchimp(db_session, business["business_id"])
    fake_client = _patch_client(monkeypatch)
    fake_client.get_campaign = AsyncMock(side_effect=MailchimpClientError("boom"))
    campaign = campaign_service.create_draft(db_session, business["business_id"], **_draft_campaign_kwargs())
    campaign.mailchimp_campaign_id = "camp1"
    campaign.status = "sending"
    db_session.commit()

    result = await campaign_service.refresh_campaign_status(db_session, business["business_id"], str(campaign.id))

    assert result.status == "sending"  # best-effort refresh: stale status kept, no raise


@pytest.mark.asyncio
async def test_get_campaign_report_requires_sent_or_sending_status(db_session, business, monkeypatch):
    _connect_mailchimp(db_session, business["business_id"])
    _patch_client(monkeypatch)
    campaign = campaign_service.create_draft(db_session, business["business_id"], **_draft_campaign_kwargs())
    campaign_service.approve_campaign(db_session, business["business_id"], str(campaign.id))

    with pytest.raises(ValueError):
        await campaign_service.get_campaign_report(db_session, business["business_id"], str(campaign.id))


@pytest.mark.asyncio
async def test_get_campaign_report_returns_live_mailchimp_numbers(db_session, business, monkeypatch):
    _connect_mailchimp(db_session, business["business_id"])
    fake_client = _patch_client(monkeypatch, get_campaign={"id": "camp1", "status": "sent", "emails_sent": 100, "send_time": None, "archive_url": None})
    campaign = campaign_service.create_draft(db_session, business["business_id"], **_draft_campaign_kwargs())
    campaign.mailchimp_campaign_id = "camp1"
    campaign.status = "sending"
    db_session.commit()

    report = await campaign_service.get_campaign_report(db_session, business["business_id"], str(campaign.id))

    fake_client.get_campaign_report.assert_awaited_once_with("camp1")
    assert report.emails_sent == 100
    assert report.open_rate == 30.0
