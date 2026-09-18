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


@pytest.fixture(autouse=True)
def _use_test_db_for_background_mailchimp_sync(monkeypatch, db_session):
    """sync_lead_to_mailchimp_background (see lead_service.py) opens its
    own SessionLocal() since it runs after the request's own session is
    closed (same reasoning document_service.crawl_and_ingest_website's own
    tests already establish, see test_website_crawl.py's use_test_db_for_
    crawl) -- redirect that to the test's isolated session so a lead
    created via `client.post("/api/leads", ...)` in these tests is found
    by the background sync too, instead of looking it up against the real
    dev database (settings.database_url) where it doesn't exist. Autouse
    here (unlike the crawl tests' opt-in fixture) because nearly every
    test in this file depends on the background sync actually running
    against the same data it just created.

    Wrapped so `.close()` is a no-op: sync_lead_to_mailchimp_background
    correctly closes ITS OWN session when done (that's the actual
    production fix), but here that session IS db_session -- letting a
    background sync mid-test tear down the one session every other part
    of the test (including a later assertion, or a second POST /api/leads
    in the same test) still needs would detach every object it holds,
    the same "finally: pass, not db.close()" reasoning conftest.py's own
    override_get_db already uses for the request-scoped dependency."""

    class _NoCloseSession:
        def __getattr__(self, name):
            return getattr(db_session, name)

        def close(self):
            pass

    monkeypatch.setattr(lead_service, "SessionLocal", lambda: _NoCloseSession())


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


def test_resubmitting_a_lead_bumps_updated_at_but_not_created_at(client, business, db_session, monkeypatch):
    """A repeat demo-form submission from the same email updates the
    EXISTING lead row rather than creating a new one (see the dedup test
    above) -- without updated_at, that change was invisible in the
    dashboard's Leads list, which sorts by created_at (never changes on
    an update), making a genuinely-just-updated lead look untouched."""
    _make_marketing(monkeypatch, business["business_id"])
    _mock_mailchimp(monkeypatch)

    payload = {"business_id": business["business_id"], "name": "Jane Doe", "email": "jane@example.com"}
    client.post("/api/leads", json=payload)
    lead = db_session.query(Lead).filter(Lead.business_id == business["business_id"]).first()
    original_created_at = lead.created_at
    original_updated_at = lead.updated_at
    assert original_updated_at is not None

    payload["message"] = "Following up on my earlier request"
    client.post("/api/leads", json=payload)

    db_session.refresh(lead)
    assert lead.created_at == original_created_at
    assert lead.updated_at > original_updated_at


def test_list_leads_includes_updated_at(client, business):
    client.post("/api/leads", json={"business_id": business["business_id"], "name": "Jane Doe", "email": "jane2@example.com"})

    resp = client.get("/api/leads", headers=business["headers"])

    assert resp.status_code == 200
    assert resp.json()[0]["updated_at"] is not None


def test_list_leads_sorts_by_updated_at_not_created_at(client, business, db_session):
    """An older lead that gets touched (e.g. a status change via PATCH)
    should float to the top of the list, not stay buried under newer,
    untouched leads -- that's the whole point of tracking updated_at."""
    client.post(
        "/api/leads", json={"business_id": business["business_id"], "name": "Older Lead", "email": "older@example.com"}
    )
    client.post(
        "/api/leads", json={"business_id": business["business_id"], "name": "Newer Lead", "email": "newer@example.com"}
    )
    older = db_session.query(Lead).filter(Lead.email == "older@example.com").first()

    client.patch(f"/api/leads/{older.id}", json={"status": "contacted"}, headers=business["headers"])

    resp = client.get("/api/leads", headers=business["headers"])

    assert resp.status_code == 200
    emails = [lead["email"] for lead in resp.json()]
    assert emails[0] == "older@example.com"


def test_resubmitting_a_consenting_lead_updates_the_existing_mailchimp_contact(client, business, db_session, monkeypatch):
    """PUT /lists/{id}/members/{hash} is Mailchimp's own "add or update"
    endpoint -- a consenting lead who resubmits the demo form (e.g. with a
    corrected company name) must re-sync to the SAME Mailchimp contact
    with the NEW field values, not just get skipped as "already synced"."""
    _make_marketing(monkeypatch, business["business_id"])
    add_or_update, _ = _mock_mailchimp(monkeypatch, contact_id="contact-existing")

    payload = {
        "business_id": business["business_id"],
        "name": "Jane Doe",
        "email": "jane@example.com",
        "company": "Acme Inc",
        "marketing_consent": True,
    }
    client.post("/api/leads", json=payload)
    assert add_or_update.call_count == 1

    payload["company"] = "Acme Corp"  # corrected on resubmission
    client.post("/api/leads", json=payload)

    assert add_or_update.call_count == 2
    second_call_merge_fields = add_or_update.call_args_list[1].args[1]
    assert second_call_merge_fields.company == "Acme Corp"

    lead = db_session.query(Lead).filter(Lead.business_id == business["business_id"]).first()
    assert lead.company == "Acme Corp"
    assert lead.mailchimp_synced is True
    assert lead.mailchimp_contact_id == "contact-existing"


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


@pytest.mark.asyncio
async def test_background_sync_looks_up_and_persists_from_just_a_lead_id(client, business, db_session, monkeypatch):
    """Regression test for a real bug found via manual testing against a
    live (non-TestClient) server: the ORIGINAL api/leads.py wiring
    scheduled background_tasks.add_task(lead_service.sync_lead_to_
    mailchimp, db, lead) -- the REQUEST's own session and ORM object.
    Against a real server, by the time that background task actually ran,
    the request's session was already closed (production's real get_db()
    does `finally: db.close()`), so `lead.mailchimp_synced = True; db.
    commit()` silently committed nothing -- no exception, "successful"
    still logged, but the leads table kept showing mailchimp_synced=false
    even though the real Mailchimp PUT had genuinely succeeded (200).

    This file's own `client`/`db_session` fixtures never close the
    session between a request and its background tasks (see conftest.py's
    override_get_db `finally: pass`), so this exact bug could never
    reproduce inside this test suite -- confirmed instead by hand against
    a real running uvicorn process (real Mailchimp call, real Postgres
    row inspected before and after the fix).

    What this automated test actually locks in: sync_lead_to_mailchimp_
    background takes ONLY a lead_id (never a caller-supplied session or
    ORM object -- the actual shape of the fix), looks the lead up itself,
    and persists the result -- proven here by calling it directly, the
    same way api/leads.py's background task does, and confirming the
    change is visible through this test's own session afterward.
    """
    _make_marketing(monkeypatch, business["business_id"])
    _mock_mailchimp(monkeypatch, contact_id="contact-bg")

    lead = Lead(
        business_id=business["business_id"], name="Background Sync", email="bg-sync@example.com",
        marketing_consent=True, status="new",
    )
    db_session.add(lead)
    db_session.commit()
    db_session.refresh(lead)
    lead_id = str(lead.id)

    await lead_service.sync_lead_to_mailchimp_background(lead_id)

    db_session.refresh(lead)
    assert lead.mailchimp_synced is True
    assert lead.mailchimp_contact_id == "contact-bg"
    assert lead.mailchimp_last_synced_at is not None


# --- Test 6: Mailchimp failure --------------------------------------------

def test_mailchimp_failure_still_returns_success_and_keeps_lead_unsynced(client, business, db_session, monkeypatch):
    from app.services.mailchimp_service import MailchimpError

    _make_marketing(monkeypatch, business["business_id"])
    _mock_mailchimp(monkeypatch, add_or_update_side_effect=MailchimpError("HTTP 500"))

    resp = client.post(
        "/api/leads",
        # marketing_consent: True -- otherwise the Mailchimp call is
        # skipped before ever reaching mailchimp_service, and this
        # wouldn't actually exercise the failure path it's named for.
        json={"business_id": business["business_id"], "name": "Jane Doe", "email": "jane@example.com", "marketing_consent": True},
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
        json={"business_id": business["business_id"], "name": "Jane Doe", "email": "jane@example.com", "marketing_consent": True},
    )

    assert resp.status_code == 201
    assert add_or_update.call_count == 1
    lead = db_session.query(Lead).filter(Lead.business_id == business["business_id"]).first()
    assert lead.mailchimp_synced is False


# --- Test 8 & 9: marketing consent ------------------------------------------
#
# NOTE: sync_lead_to_mailchimp now skips the Mailchimp call ENTIRELY when
# marketing_consent is false (see lead_service.py's own docstring on this
# -- a deliberate narrowing of the original design, where a non-consenting
# lead was still synced as a Mailchimp "transactional" contact). Tests
# below that exercise an actual Mailchimp call now explicitly opt in with
# marketing_consent: True.

def test_marketing_consent_false_skips_mailchimp_entirely(client, business, monkeypatch):
    """Superseded the old 'sent as non-marketing (transactional)'
    behavior -- see this file's own note above. A lead who left the
    consent box unchecked must never have their email sent to Mailchimp
    at all, not even as a non-marketed-to contact."""
    _make_marketing(monkeypatch, business["business_id"])
    add_or_update, add_tags = _mock_mailchimp(monkeypatch)

    resp = client.post(
        "/api/leads",
        json={
            "business_id": business["business_id"],
            "name": "Jane Doe",
            "email": "jane@example.com",
            "marketing_consent": False,
        },
    )

    assert resp.status_code == 201
    add_or_update.assert_not_called()
    add_tags.assert_not_called()


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


# --- Step 3 (auto-enroll demo bookers): the three scenarios asked for -------
#
# 1. Opt-in checked -> lead created -> Mailchimp sync made, with the right
#    audience id (settings.mailchimp_audience_id, via _make_marketing) and
#    the right contact fields -- end-to-end at the httpx boundary (same
#    _FakeClient idiom as test_mailchimp_payload_never_carries_a_bare_
#    status_for_a_marketing_lead above), not just "some mock was called",
#    so this actually proves the real audience id lands in the request URL.
# 2. Opt-in unchecked -> lead created -> Mailchimp sync NOT made (see
#    test_marketing_consent_false_skips_mailchimp_entirely above).
# 3. Mailchimp call fails, opt-in checked -> demo booking still succeeds
#    (see test_mailchimp_failure_still_returns_success_and_keeps_lead_
#    unsynced above, now updated to actually exercise this path).


def test_consenting_demo_lead_syncs_to_the_configured_audience_with_contact_fields(client, business, db_session, monkeypatch):
    from unittest.mock import AsyncMock

    _make_marketing(monkeypatch, business["business_id"])
    captured_url = {}
    captured_body = {}

    async def fake_put(url, **kwargs):
        captured_url["value"] = url
        captured_body.update(kwargs.get("json", {}))
        return type("R", (), {"status_code": 200, "json": lambda self: {"id": "contact-1"}})()

    class _FakeClient:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            return False

        put = staticmethod(fake_put)

    monkeypatch.setattr(lead_service.mailchimp_service.httpx, "AsyncClient", lambda **_: _FakeClient())
    add_tags = AsyncMock()
    monkeypatch.setattr(lead_service.mailchimp_service, "add_tags_to_contact", add_tags)

    resp = client.post(
        "/api/leads",
        json={
            "business_id": business["business_id"],
            "name": "Jane Doe",
            "first_name": "Jane",
            "last_name": "Doe",
            "email": "jane@example.com",
            "company": "Acme Inc",
            "phone": "+47 555 0100",
            "industry": "Restaurant",
            "interest": "AI Voice Agent",
            "marketing_consent": True,
        },
    )

    assert resp.status_code == 201
    # settings.mailchimp_audience_id is "test-audience" (see _make_marketing)
    # -- this is Mielikkix's OWN single-account audience, not a per-tenant
    # Option A campaign audience (those are two separate integrations, see
    # lead_service.py's own module docstring).
    assert "/lists/test-audience/members/" in captured_url["value"]
    assert captured_body["email_address"] == "jane@example.com"
    assert captured_body["merge_fields"] == {
        "FNAME": "Jane", "LNAME": "Doe", "COMPANY": "Acme Inc",
        "PHONE": "+47 555 0100", "INDUSTRY": "Restaurant", "INTEREST": "AI Voice Agent",
    }
    lead = db_session.query(Lead).filter(Lead.business_id == business["business_id"]).first()
    assert lead.mailchimp_synced is True
    add_tags.assert_awaited_once()


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
            "marketing_consent": True,
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
            "marketing_consent": True,
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

    # marketing_consent=True -- otherwise sync_lead_to_mailchimp now skips
    # the call before this endpoint has anything to retry (see that
    # function's own docstring).
    lead = Lead(business_id=business["business_id"], name="Jane Doe", email="jane@example.com", marketing_consent=True)
    db_session.add(lead)
    db_session.commit()
    db_session.refresh(lead)

    resp = client.post(f"/api/leads/{lead.id}/sync-mailchimp", headers=business["headers"])

    assert resp.status_code == 200, resp.text
    assert resp.json()["mailchimp_synced"] is True


def test_manual_mailchimp_retry_endpoint_skips_without_consent(client, business, db_session, monkeypatch):
    _make_marketing(monkeypatch, business["business_id"])
    add_or_update, _ = _mock_mailchimp(monkeypatch)

    lead = Lead(business_id=business["business_id"], name="Jane Doe", email="jane@example.com", marketing_consent=False)
    db_session.add(lead)
    db_session.commit()
    db_session.refresh(lead)

    resp = client.post(f"/api/leads/{lead.id}/sync-mailchimp", headers=business["headers"])

    assert resp.status_code == 200, resp.text
    assert resp.json()["mailchimp_synced"] is False
    add_or_update.assert_not_called()
