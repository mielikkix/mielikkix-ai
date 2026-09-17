"""app/api/campaigns.py -- HTTP wrapper for the Email Marketing Agent's
campaigns. CRUD/approve are exercised against the real DB + campaign_
service (no Mailchimp call involved); send/schedule/test/report mock
campaign_service's own async functions (already covered against a faked
MailchimpClient in test_campaign_service.py) so this file stays focused on
routing, auth, entitlement gating, and HTTP status-code mapping -- same
split test_mailchimp_oauth.py uses between itself and test_mailchimp_
client.py.
"""

from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock

import pytest

from app.services import campaign_service
from app.services.campaign_service import CampaignSendError


def _entitle(business, set_plan):
    set_plan(business["business_id"], "business")


# --- entitlement gating ---------------------------------------------------


def test_list_campaigns_requires_email_marketing_enabled_plan(client, business):
    resp = client.get("/api/businesses/me/campaigns", headers=business["headers"])

    assert resp.status_code == 403


def test_create_campaign_requires_login(client):
    resp = client.post("/api/businesses/me/campaigns", json={})

    assert resp.status_code == 401


# --- CRUD (real DB, no Mailchimp involved) --------------------------------


def test_create_and_get_campaign(client, business, set_plan):
    _entitle(business, set_plan)

    create_resp = client.post(
        "/api/businesses/me/campaigns", headers=business["headers"],
        json={"subject": "Hello", "body_html": "<p>hi</p>"},
    )
    assert create_resp.status_code == 200
    campaign_id = create_resp.json()["id"]
    assert create_resp.json()["status"] == "draft"

    get_resp = client.get(f"/api/businesses/me/campaigns/{campaign_id}", headers=business["headers"])
    assert get_resp.status_code == 200
    assert get_resp.json()["subject"] == "Hello"


def test_get_nonexistent_campaign_404s(client, business, set_plan):
    _entitle(business, set_plan)

    resp = client.get(
        "/api/businesses/me/campaigns/00000000-0000-0000-0000-000000000000", headers=business["headers"]
    )

    assert resp.status_code == 404


def test_list_campaigns_scoped_to_tenant(client, business, signup, set_plan):
    _entitle(business, set_plan)
    other = signup()
    set_plan(other["business_id"], "business")
    client.post("/api/businesses/me/campaigns", headers=other["headers"], json={"subject": "Not yours"})

    resp = client.get("/api/businesses/me/campaigns", headers=business["headers"])

    assert resp.status_code == 200
    assert resp.json() == []


def test_get_another_tenants_campaign_404s(client, business, signup, set_plan):
    _entitle(business, set_plan)
    other = signup()
    set_plan(other["business_id"], "business")
    other_campaign = client.post("/api/businesses/me/campaigns", headers=other["headers"], json={"subject": "Not yours"}).json()

    resp = client.get(f"/api/businesses/me/campaigns/{other_campaign['id']}", headers=business["headers"])

    assert resp.status_code == 404


def test_update_draft_campaign(client, business, set_plan):
    _entitle(business, set_plan)
    campaign_id = client.post("/api/businesses/me/campaigns", headers=business["headers"], json={"subject": "Old"}).json()["id"]

    resp = client.patch(f"/api/businesses/me/campaigns/{campaign_id}", headers=business["headers"], json={"subject": "New"})

    assert resp.status_code == 200
    assert resp.json()["subject"] == "New"


def test_approve_campaign_missing_fields_returns_400(client, business, set_plan):
    _entitle(business, set_plan)
    campaign_id = client.post("/api/businesses/me/campaigns", headers=business["headers"], json={"subject": "Old"}).json()["id"]

    resp = client.post(f"/api/businesses/me/campaigns/{campaign_id}/approve", headers=business["headers"])

    assert resp.status_code == 400


def test_approve_campaign_success(client, business, set_plan):
    _entitle(business, set_plan)
    campaign_id = client.post(
        "/api/businesses/me/campaigns", headers=business["headers"],
        json={"subject": "Hi", "body_html": "<p>hi</p>", "reply_to": "owner@acme.com", "mailchimp_audience_id": "aud1"},
    ).json()["id"]

    resp = client.post(f"/api/businesses/me/campaigns/{campaign_id}/approve", headers=business["headers"])

    assert resp.status_code == 200
    assert resp.json()["status"] == "approved"


# --- send / schedule / test / report (campaign_service mocked) -----------


def _make_campaign(client, business):
    return client.post(
        "/api/businesses/me/campaigns", headers=business["headers"],
        json={"subject": "Hi", "body_html": "<p>hi</p>", "reply_to": "owner@acme.com", "mailchimp_audience_id": "aud1"},
    ).json()["id"]


def test_send_campaign_value_error_maps_to_400(client, business, set_plan, monkeypatch):
    _entitle(business, set_plan)
    campaign_id = _make_campaign(client, business)
    monkeypatch.setattr(campaign_service, "send_campaign", AsyncMock(side_effect=ValueError("not approved")))

    resp = client.post(f"/api/businesses/me/campaigns/{campaign_id}/send", headers=business["headers"])

    assert resp.status_code == 400
    assert resp.json()["detail"] == "not approved"


def test_send_campaign_upstream_failure_maps_to_502(client, business, set_plan, monkeypatch):
    _entitle(business, set_plan)
    campaign_id = _make_campaign(client, business)
    monkeypatch.setattr(campaign_service, "send_campaign", AsyncMock(side_effect=CampaignSendError("mailchimp down")))

    resp = client.post(f"/api/businesses/me/campaigns/{campaign_id}/send", headers=business["headers"])

    assert resp.status_code == 502
    assert resp.json()["detail"] == "mailchimp down"


def test_send_campaign_success_returns_updated_campaign(client, business, set_plan, monkeypatch, db_session):
    _entitle(business, set_plan)
    campaign_id = _make_campaign(client, business)

    async def _fake_send(db, business_id, cid):
        from app.models.campaign import Campaign

        c = db.query(Campaign).filter(Campaign.id == cid).first()
        c.status = "sending"
        c.mailchimp_campaign_id = "camp1"
        db.commit()
        db.refresh(c)
        return c

    monkeypatch.setattr(campaign_service, "send_campaign", _fake_send)

    resp = client.post(f"/api/businesses/me/campaigns/{campaign_id}/send", headers=business["headers"])

    assert resp.status_code == 200
    assert resp.json()["status"] == "sending"
    assert resp.json()["mailchimp_campaign_id"] == "camp1"


def test_schedule_campaign_maps_errors(client, business, set_plan, monkeypatch):
    _entitle(business, set_plan)
    campaign_id = _make_campaign(client, business)
    monkeypatch.setattr(campaign_service, "schedule_campaign", AsyncMock(side_effect=ValueError("must be in the future")))
    future = (datetime.now(timezone.utc) + timedelta(days=1)).isoformat()

    resp = client.post(
        f"/api/businesses/me/campaigns/{campaign_id}/schedule", headers=business["headers"], json={"scheduled_at": future}
    )

    assert resp.status_code == 400


def test_send_test_email_maps_errors(client, business, set_plan, monkeypatch):
    _entitle(business, set_plan)
    campaign_id = _make_campaign(client, business)
    monkeypatch.setattr(campaign_service, "send_test_email", AsyncMock(side_effect=CampaignSendError("mailchimp down")))

    resp = client.post(
        f"/api/businesses/me/campaigns/{campaign_id}/test", headers=business["headers"], json={"test_emails": ["a@example.com"]}
    )

    assert resp.status_code == 502


def test_get_campaign_report_success(client, business, set_plan, monkeypatch):
    _entitle(business, set_plan)
    campaign_id = _make_campaign(client, business)

    from app.integrations.email_marketing_providers import CampaignReport

    fake_report = CampaignReport(
        emails_sent=100, opens_total=40, unique_opens=30, open_rate=30.0,
        click_rate=5.0, unsubscribed=1, hard_bounces=0, soft_bounces=1,
    )
    monkeypatch.setattr(campaign_service, "get_campaign_report", AsyncMock(return_value=fake_report))

    resp = client.get(f"/api/businesses/me/campaigns/{campaign_id}/report", headers=business["headers"])

    assert resp.status_code == 200
    assert resp.json() == {
        "emails_sent": 100, "opens_total": 40, "unique_opens": 30, "open_rate": 30.0,
        "click_rate": 5.0, "unsubscribed": 1, "hard_bounces": 0, "soft_bounces": 1,
    }


def test_get_campaign_report_not_sent_yet_maps_to_400(client, business, set_plan, monkeypatch):
    _entitle(business, set_plan)
    campaign_id = _make_campaign(client, business)
    monkeypatch.setattr(campaign_service, "get_campaign_report", AsyncMock(side_effect=ValueError("not sent yet")))

    resp = client.get(f"/api/businesses/me/campaigns/{campaign_id}/report", headers=business["headers"])

    assert resp.status_code == 400


# --- auth on every route ---------------------------------------------------


@pytest.mark.parametrize(
    "method,path",
    [
        ("get", "/api/businesses/me/campaigns"),
        ("post", "/api/businesses/me/campaigns"),
        ("get", "/api/businesses/me/campaigns/x"),
        ("patch", "/api/businesses/me/campaigns/x"),
        ("post", "/api/businesses/me/campaigns/x/approve"),
        ("post", "/api/businesses/me/campaigns/x/test"),
        ("post", "/api/businesses/me/campaigns/x/send"),
        ("post", "/api/businesses/me/campaigns/x/schedule"),
        ("get", "/api/businesses/me/campaigns/x/report"),
    ],
)
def test_every_route_requires_authentication(client, method, path):
    resp = getattr(client, method)(path)

    assert resp.status_code == 401
