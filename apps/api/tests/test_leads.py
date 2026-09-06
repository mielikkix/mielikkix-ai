"""POST/GET/PATCH /api/leads -- the public marketing "Book a Free Demo" lead
capture (website/src/pages/demo.astro) shares this same router/table with
every tenant's own chat-widget lead capture (apps/dashboard/src/widget/
LeadForm.tsx), so these tests cover both: the generic, always-worked
contract AND the new Mailchimp-sync behavior, which is scoped to exactly
one configured business_id (see app/services/lead_service.py's
is_marketing_business). Mailchimp itself is mocked at the
mailchimp_service module boundary -- same "mock at the seam, not at
httpx" idiom as test_agents_booking.py mocking _calendar_provider.
"""

from unittest.mock import AsyncMock

import pytest

from app.core.config import settings
from app.models.lead import Lead
from app.services import lead_service


@pytest.fixture(autouse=True)
def _no_real_email_provider(monkeypatch):
    """create_lead's notify_new_lead background task fires for every
    business signed up via the `business`/`signup` fixture (they always
    get a contact_email) -- this repo's real .env has a non-empty (but
    fake) RESEND_API_KEY, which makes get_notification_provider() pick
    ResendNotificationProvider and attempt a REAL network call per test
    otherwise. Forcing it empty here keeps this file on the fast, offline
    ConsoleNotificationProvider fallback, same as every other test file
    that exercises a code path touching notifications."""
    monkeypatch.setattr(settings, "resend_api_key", "")


def _make_marketing(monkeypatch, business_id: str):
    """Marks `business_id` as settings.mailchimp_sync_business_id (the one
    tenant whose leads get synced) AND satisfies mailchimp_service.is_configured()
    so lead_service actually attempts a sync instead of skipping it."""
    monkeypatch.setattr(settings, "mailchimp_sync_business_id", business_id)
    monkeypatch.setattr(settings, "mailchimp_api_key", "test-key")
    monkeypatch.setattr(settings, "mailchimp_server_prefix", "us21")
    monkeypatch.setattr(settings, "mailchimp_audience_id", "test-audience")


def _mock_mailchimp(monkeypatch, contact_id="contact-123", add_or_update_side_effect=None, add_tags_side_effect=None):
    add_or_update = AsyncMock(return_value=contact_id, side_effect=add_or_update_side_effect)
    add_tags = AsyncMock(side_effect=add_tags_side_effect)
    monkeypatch.setattr(lead_service.mailchimp_service, "add_or_update_contact", add_or_update)
    monkeypatch.setattr(lead_service.mailchimp_service, "add_tags_to_contact", add_tags)
    return add_or_update, add_tags


# --- Test 1: valid lead ------------------------------------------------

def test_create_lead_valid_returns_201_and_saves_to_db(client, business, db_session):
    resp = client.post(
        "/api/leads",
        json={
            "business_id": business["business_id"],
            "name": "Test Visitor",
            "email": "visitor@example.com",
            "phone": "+47 555 0100",
            "message": "Interested in catering for 50 people",
        },
    )

    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body == {"success": True, "message": "Thank you. Your demo request has been received."}

    lead = db_session.query(Lead).filter(Lead.business_id == business["business_id"]).first()
    assert lead is not None
    assert lead.email == "visitor@example.com"


# --- Test 2: invalid email ----------------------------------------------
# FastAPI's own validation-failure status is 422 (not the wireframe's 400) --
# already the existing, live contract (see apps/dashboard/src/widget/
# LeadForm.tsx's `Array.isArray(detail)` branch, which exists specifically
# to render this exact 422 shape) -- preserved here rather than changed.

def test_create_lead_invalid_email_is_rejected_without_mailchimp_call(client, business, monkeypatch):
    add_or_update, _ = _mock_mailchimp(monkeypatch)
    _make_marketing(monkeypatch, business["business_id"])

    resp = client.post(
        "/api/leads",
        json={"business_id": business["business_id"], "name": "Test", "email": "not-an-email"},
    )

    assert resp.status_code == 422
    add_or_update.assert_not_called()


# --- Test 3: missing required field -------------------------------------

def test_create_lead_missing_name_is_rejected(client, business):
    resp = client.post(
        "/api/leads",
        json={"business_id": business["business_id"], "email": "visitor@example.com"},
    )

    assert resp.status_code == 422


# --- Test 4: duplicate email --------------------------------------------

def test_duplicate_email_on_marketing_business_updates_existing_lead(client, business, db_session, monkeypatch):
    _make_marketing(monkeypatch, business["business_id"])
    _mock_mailchimp(monkeypatch)

    payload = {
        "business_id": business["business_id"],
        "name": "Jane Doe",
        "first_name": "Jane",
        "last_name": "Doe",
        "email": "Jane@Example.com",
        "company": "Acme Inc",
    }
    client.post("/api/leads", json=payload)
    payload["message"] = "Following up on my earlier request"
    client.post("/api/leads", json=payload)

    leads = db_session.query(Lead).filter(Lead.business_id == business["business_id"]).all()
    assert len(leads) == 1
    assert leads[0].email == "jane@example.com"
    assert leads[0].message == "Following up on my earlier request"


def test_duplicate_email_on_a_normal_tenant_still_creates_a_new_lead_each_time(client, business, db_session):
    """Regression guard: a normal tenant's chat widget (any business_id
    other than settings.mailchimp_sync_business_id) must keep its
    existing behavior of one Lead row per submission -- this feature must
    not change that for the live product."""
    payload = {
        "business_id": business["business_id"],
        "name": "Repeat Visitor",
        "email": "repeat@example.com",
    }
    client.post("/api/leads", json=payload)
    client.post("/api/leads", json=payload)

    leads = db_session.query(Lead).filter(Lead.business_id == business["business_id"]).all()
    assert len(leads) == 2


# --- Test 5: Mailchimp success -------------------------------------------

def test_mailchimp_success_marks_lead_synced(client, business, db_session, monkeypatch):
    _make_marketing(monkeypatch, business["business_id"])
    _mock_mailchimp(monkeypatch, contact_id="contact-abc")

    resp = client.post(
        "/api/leads",
        json={
            "business_id": business["business_id"],
            "name": "Jane Doe",
            "email": "jane@example.com",
            "marketing_consent": True,
        },
    )

    assert resp.status_code == 201
    lead = db_session.query(Lead).filter(Lead.business_id == business["business_id"]).first()
    assert lead.mailchimp_synced is True
    assert lead.mailchimp_contact_id == "contact-abc"
    assert lead.mailchimp_last_synced_at is not None


# --- Test 6: Mailchimp failure --------------------------------------------

def test_mailchimp_failure_still_returns_success_and_keeps_lead_unsynced(client, business, db_session, monkeypatch):
    from app.services.mailchimp_service import MailchimpError

    _make_marketing(monkeypatch, business["business_id"])
    _mock_mailchimp(monkeypatch, add_or_update_side_effect=MailchimpError("HTTP 500"))

    resp = client.post(
        "/api/leads",
        json={"business_id": business["business_id"], "name": "Jane Doe", "email": "jane@example.com"},
    )

    assert resp.status_code == 201
    assert resp.json()["success"] is True
    lead = db_session.query(Lead).filter(Lead.business_id == business["business_id"]).first()
    assert lead is not None
    assert lead.mailchimp_synced is False


# --- Test 7: Mailchimp 429 -------------------------------------------------

def test_mailchimp_rate_limit_does_not_retry_in_request(client, business, db_session, monkeypatch):
    from app.services.mailchimp_service import MailchimpRateLimitError

    _make_marketing(monkeypatch, business["business_id"])
    add_or_update, _ = _mock_mailchimp(monkeypatch, add_or_update_side_effect=MailchimpRateLimitError("429"))

    resp = client.post(
        "/api/leads",
        json={"business_id": business["business_id"], "name": "Jane Doe", "email": "jane@example.com"},
    )

    assert resp.status_code == 201
    assert add_or_update.call_count == 1
    lead = db_session.query(Lead).filter(Lead.business_id == business["business_id"]).first()
    assert lead.mailchimp_synced is False


# --- Test 8 & 9: marketing consent ------------------------------------------

def test_marketing_consent_false_is_sent_as_non_marketing(client, business, monkeypatch):
    _make_marketing(monkeypatch, business["business_id"])
    add_or_update, _ = _mock_mailchimp(monkeypatch)

    client.post(
        "/api/leads",
        json={
            "business_id": business["business_id"],
            "name": "Jane Doe",
            "email": "jane@example.com",
            "marketing_consent": False,
        },
    )

    assert add_or_update.await_args.args[2] is False


def test_marketing_consent_true_is_sent_as_marketing(client, business, monkeypatch):
    _make_marketing(monkeypatch, business["business_id"])
    add_or_update, _ = _mock_mailchimp(monkeypatch)

    client.post(
        "/api/leads",
        json={
            "business_id": business["business_id"],
            "name": "Jane Doe",
            "email": "jane@example.com",
            "marketing_consent": True,
        },
    )

    assert add_or_update.await_args.args[2] is True


# --- Explicit consent semantics (add-on brief) ------------------------------
# Requesting a demo and consenting to marketing are two separate actions --
# these tests lock in that a lead is always stored (with or without
# consent), that explicit consent is recorded durably, and that consent is
# a one-way flag this flow can only ever turn ON, never accidentally OFF.

def test_new_lead_without_consent_stores_marketing_consent_false(client, business, db_session, monkeypatch):
    _make_marketing(monkeypatch, business["business_id"])
    _mock_mailchimp(monkeypatch)

    resp = client.post(
        "/api/leads",
        json={"business_id": business["business_id"], "name": "Jane Doe", "email": "jane@example.com"},
    )

    assert resp.status_code == 201
    lead = db_session.query(Lead).filter(Lead.business_id == business["business_id"]).first()
    assert lead.marketing_consent is False
    assert lead.marketing_consent_at is None


def test_explicit_consent_records_true_and_a_timestamp(client, business, db_session, monkeypatch):
    _make_marketing(monkeypatch, business["business_id"])
    _mock_mailchimp(monkeypatch)

    resp = client.post(
        "/api/leads",
        json={
            "business_id": business["business_id"],
            "name": "Jane Doe",
            "email": "jane@example.com",
            "marketing_consent": True,
        },
    )

    assert resp.status_code == 201
    lead = db_session.query(Lead).filter(Lead.business_id == business["business_id"]).first()
    assert lead.marketing_consent is True
    assert lead.marketing_consent_at is not None


def test_later_unchecked_submission_does_not_downgrade_earlier_consent(client, business, db_session, monkeypatch):
    """Critical regression guard: a lead who consented once and later
    resubmits the demo form with the box unchecked must NOT have their
    consent silently withdrawn -- an unchecked box just means "no new
    consent action", not "revoke consent"."""
    _make_marketing(monkeypatch, business["business_id"])
    _mock_mailchimp(monkeypatch)

    client.post(
        "/api/leads",
        json={
            "business_id": business["business_id"],
            "name": "Jane Doe",
            "email": "jane@example.com",
            "marketing_consent": True,
        },
    )
    lead = db_session.query(Lead).filter(Lead.business_id == business["business_id"]).first()
    first_consented_at = lead.marketing_consent_at
    assert first_consented_at is not None

    client.post(
        "/api/leads",
        json={
            "business_id": business["business_id"],
            "name": "Jane Doe",
            "email": "jane@example.com",
            "marketing_consent": False,
        },
    )

    db_session.refresh(lead)
    assert lead.marketing_consent is True
    assert lead.marketing_consent_at == first_consented_at


def test_mailchimp_payload_never_carries_a_bare_status_for_a_marketing_lead(client, business, monkeypatch):
    """End-to-end version of test_mailchimp_service.py's own check: even
    going through the full create_lead -> lead_service -> mailchimp_service
    path, no bare `status` field (only `status_if_new`) ever reaches
    Mailchimp -- the mechanism that keeps an existing unsubscribed
    contact from being silently resubscribed by a later consenting
    submission."""
    from unittest.mock import AsyncMock

    _make_marketing(monkeypatch, business["business_id"])
    captured = {}

    async def fake_put(url, **kwargs):
        captured.update(kwargs.get("json", {}))
        return type("R", (), {"status_code": 200, "json": lambda self: {"id": "contact-1"}})()

    class _FakeClient:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            return False

        put = staticmethod(fake_put)

    monkeypatch.setattr(lead_service.mailchimp_service.httpx, "AsyncClient", lambda **_: _FakeClient())
    monkeypatch.setattr(lead_service.mailchimp_service, "add_tags_to_contact", AsyncMock())

    client.post(
        "/api/leads",
        json={
            "business_id": business["business_id"],
            "name": "Jane Doe",
            "email": "jane@example.com",
            "marketing_consent": True,
        },
    )

    assert "status" not in captured
    assert captured.get("status_if_new") == "pending"


# --- Test 10 & 11: tags -----------------------------------------------------

def test_interest_tag_is_applied(client, business, monkeypatch):
    _make_marketing(monkeypatch, business["business_id"])
    _, add_tags = _mock_mailchimp(monkeypatch)

    client.post(
        "/api/leads",
        json={
            "business_id": business["business_id"],
            "name": "Jane Doe",
            "email": "jane@example.com",
            "interest": "AI Voice Agent",
        },
    )

    tags = add_tags.await_args.args[1]
    assert "AGENT_VOICE" in tags
    assert {"LEAD", "DEMO_REQUESTED", "SOURCE_WEBSITE"}.issubset(set(tags))


def test_industry_tag_is_applied(client, business, monkeypatch):
    _make_marketing(monkeypatch, business["business_id"])
    _, add_tags = _mock_mailchimp(monkeypatch)

    client.post(
        "/api/leads",
        json={
            "business_id": business["business_id"],
            "name": "Jane Doe",
            "email": "jane@example.com",
            "industry": "Restaurant",
        },
    )

    tags = add_tags.await_args.args[1]
    assert "INDUSTRY_RESTAURANT" in tags


# --- Test 12: credentials never exposed -------------------------------------

def test_mailchimp_credentials_never_appear_in_response(client, business, monkeypatch):
    monkeypatch.setattr(settings, "mailchimp_api_key", "super-secret-key")
    resp = client.post(
        "/api/leads",
        json={"business_id": business["business_id"], "name": "Jane Doe", "email": "jane@example.com"},
    )

    assert "super-secret-key" not in resp.text


# --- Gating: non-marketing businesses are never sent to Mailchimp -----------

def test_non_marketing_business_never_calls_mailchimp(client, business, monkeypatch):
    # settings.mailchimp_sync_business_id intentionally left unset/different
    # from `business` -- this must be the default, safe behavior.
    monkeypatch.setattr(settings, "mailchimp_sync_business_id", "00000000-0000-0000-0000-000000000000")
    add_or_update, add_tags = _mock_mailchimp(monkeypatch)

    resp = client.post(
        "/api/leads",
        json={"business_id": business["business_id"], "name": "Jane Doe", "email": "jane@example.com"},
    )

    assert resp.status_code == 201
    add_or_update.assert_not_called()
    add_tags.assert_not_called()


# --- Manual retry endpoint ---------------------------------------------------

def test_manual_mailchimp_retry_endpoint_requires_auth(client):
    resp = client.post("/api/leads/00000000-0000-0000-0000-000000000000/sync-mailchimp")
    assert resp.status_code == 401


def test_manual_mailchimp_retry_endpoint_syncs_lead(client, business, db_session, monkeypatch):
    _make_marketing(monkeypatch, business["business_id"])
    _mock_mailchimp(monkeypatch, contact_id="retried-contact")

    lead = Lead(business_id=business["business_id"], name="Jane Doe", email="jane@example.com")
    db_session.add(lead)
    db_session.commit()
    db_session.refresh(lead)

    resp = client.post(f"/api/leads/{lead.id}/sync-mailchimp", headers=business["headers"])

    assert resp.status_code == 200, resp.text
    assert resp.json()["mailchimp_synced"] is True
