"""Unit tests for app/services/mailchimp_service.py -- mocked at the
httpx.AsyncClient boundary (no real network call, no real Mailchimp
account needed), same "mock at the boundary" idiom as
test_google_calendar_client.py's _FakePost for `requests.post`.
"""

import hashlib

import httpx
import pytest

from app.core.config import settings
from app.services import mailchimp_service
from app.services.mailchimp_service import (
    MailchimpError,
    MailchimpRateLimitError,
    MergeFields,
)


class _FakeResponse:
    def __init__(self, status_code: int, json_data: dict | None = None, text: str = ""):
        self.status_code = status_code
        self._json_data = json_data or {}
        self.text = text

    def json(self):
        return self._json_data


class _FakeAsyncClient:
    """Records the last call made through it and returns a canned
    response/exception -- mirrors _FakePost in test_google_calendar_client.py."""

    def __init__(self, response=None, exc=None):
        self._response = response
        self._exc = exc
        self.last_url = None
        self.last_kwargs = None

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc_info):
        return False

    async def _call(self, url, **kwargs):
        self.last_url = url
        self.last_kwargs = kwargs
        if self._exc:
            raise self._exc
        return self._response

    async def put(self, url, **kwargs):
        return await self._call(url, **kwargs)

    async def post(self, url, **kwargs):
        return await self._call(url, **kwargs)


def _configure(monkeypatch):
    monkeypatch.setattr(settings, "mailchimp_api_key", "test-secret-key")
    monkeypatch.setattr(settings, "mailchimp_server_prefix", "us21")
    monkeypatch.setattr(settings, "mailchimp_audience_id", "audience-1")


def _install_fake_client(monkeypatch, **kwargs):
    fake_client = _FakeAsyncClient(**kwargs)
    monkeypatch.setattr(mailchimp_service.httpx, "AsyncClient", lambda **_: fake_client)
    return fake_client


def test_subscriber_hash_is_md5_of_lowercased_trimmed_email():
    expected = hashlib.md5(b"visitor@example.com").hexdigest()
    assert mailchimp_service.subscriber_hash("  Visitor@Example.com  ") == expected


def test_is_configured_false_when_any_value_missing(monkeypatch):
    _configure(monkeypatch)
    monkeypatch.setattr(settings, "mailchimp_audience_id", "")
    assert mailchimp_service.is_configured() is False


def test_is_configured_true_when_all_three_set(monkeypatch):
    _configure(monkeypatch)
    assert mailchimp_service.is_configured() is True


def test_merge_fields_omits_empty_values():
    fields = MergeFields(first_name="Jane", last_name="", company="Acme", industry="", interest="")
    assert fields.to_payload() == {"FNAME": "Jane", "COMPANY": "Acme"}


@pytest.mark.asyncio
async def test_add_or_update_contact_requires_configuration(monkeypatch):
    monkeypatch.setattr(settings, "mailchimp_api_key", "")
    with pytest.raises(MailchimpError):
        await mailchimp_service.add_or_update_contact("a@example.com", MergeFields(), True)


@pytest.mark.asyncio
async def test_add_or_update_contact_success_returns_contact_id(monkeypatch):
    _configure(monkeypatch)
    fake_client = _install_fake_client(monkeypatch, response=_FakeResponse(200, {"id": "contact-1"}))

    contact_id = await mailchimp_service.add_or_update_contact(
        "Visitor@Example.com", MergeFields(first_name="V"), True
    )

    assert contact_id == "contact-1"
    assert fake_client.last_kwargs["json"]["email_address"] == "visitor@example.com"
    assert fake_client.last_kwargs["auth"] == ("anystring", "test-secret-key")


# --- Double Opt-In: a newly-consenting contact must go through Mailchimp's
# own confirmation flow, never be immediately "subscribed" from the API ---

@pytest.mark.asyncio
async def test_consenting_contact_is_sent_as_pending_not_subscribed(monkeypatch):
    """The core Double Opt-In requirement: setting status_if_new="subscribed"
    via the API always bypasses an audience's Double Opt-In setting, no
    matter how that audience is configured in the Mailchimp UI. "pending"
    is the only status that makes Mailchimp actually send its own
    confirmation email and hold the contact unconfirmed until they click
    it. This test inspects the REAL payload mailchimp_service builds --
    it does not just trust that the implementation is correct."""
    _configure(monkeypatch)
    fake_client = _install_fake_client(monkeypatch, response=_FakeResponse(200, {"id": "contact-1"}))

    await mailchimp_service.add_or_update_contact("visitor@example.com", MergeFields(), True)

    assert fake_client.last_kwargs["json"]["status_if_new"] == "pending"
    assert fake_client.last_kwargs["json"]["status_if_new"] != "subscribed"


@pytest.mark.asyncio
async def test_exact_payload_for_no_consent_vs_explicit_consent(monkeypatch, capsys):
    """Direct A/B proof requested after the Double Opt-In correction:
    capture and print the LITERAL JSON body sent for (A) a new lead
    without marketing consent and (B) a new lead with explicit marketing
    consent, and assert on the exact values -- not on a mocked stand-in
    for the implementation."""
    _configure(monkeypatch)

    fake_client_a = _install_fake_client(monkeypatch, response=_FakeResponse(200, {"id": "contact-a"}))
    await mailchimp_service.add_or_update_contact("no-consent@example.com", MergeFields(first_name="A"), False)
    payload_a = fake_client_a.last_kwargs["json"]

    fake_client_b = _install_fake_client(monkeypatch, response=_FakeResponse(200, {"id": "contact-b"}))
    await mailchimp_service.add_or_update_contact("consenting@example.com", MergeFields(first_name="B"), True)
    payload_b = fake_client_b.last_kwargs["json"]

    print(f"\nA) no consent   -> {payload_a}")
    print(f"B) with consent -> {payload_b}")

    assert "status" not in payload_a and "status" not in payload_b
    assert payload_a["status_if_new"] == "transactional"
    assert payload_b["status_if_new"] == "pending"
    assert payload_b["status_if_new"] != "subscribed"


@pytest.mark.asyncio
async def test_add_or_update_contact_without_consent_is_transactional(monkeypatch):
    _configure(monkeypatch)
    fake_client = _install_fake_client(monkeypatch, response=_FakeResponse(200, {"id": "contact-1"}))

    await mailchimp_service.add_or_update_contact("a@example.com", MergeFields(), False)

    assert fake_client.last_kwargs["json"]["status_if_new"] == "transactional"


@pytest.mark.asyncio
@pytest.mark.parametrize("marketing_consent", [True, False])
async def test_add_or_update_contact_never_sends_a_bare_status_field(monkeypatch, marketing_consent):
    """The other half of the Double Opt-In / no-silent-resubscribe
    guarantee: this payload must only ever carry `status_if_new` (which
    Mailchimp only applies when CREATING a brand-new member), never a
    bare `status` key. Mailchimp applies a `status` value to an EXISTING
    member unconditionally -- sending one here would let a resubmitted
    demo form silently resubscribe someone who explicitly unsubscribed
    themselves, or silently unsubscribe a real existing subscriber.
    Checked for both consent values, since this must hold regardless."""
    _configure(monkeypatch)
    fake_client = _install_fake_client(monkeypatch, response=_FakeResponse(200, {"id": "contact-1"}))

    await mailchimp_service.add_or_update_contact("a@example.com", MergeFields(), marketing_consent)

    assert "status" not in fake_client.last_kwargs["json"]


@pytest.mark.asyncio
async def test_add_or_update_contact_rate_limit_raises_specific_error(monkeypatch):
    _configure(monkeypatch)
    _install_fake_client(monkeypatch, response=_FakeResponse(429, text="rate limited"))

    with pytest.raises(MailchimpRateLimitError):
        await mailchimp_service.add_or_update_contact("a@example.com", MergeFields(), True)


@pytest.mark.asyncio
@pytest.mark.parametrize("status_code", [400, 401, 404, 500])
async def test_add_or_update_contact_http_error_statuses(monkeypatch, status_code):
    _configure(monkeypatch)
    _install_fake_client(monkeypatch, response=_FakeResponse(status_code, text="error body"))

    with pytest.raises(MailchimpError):
        await mailchimp_service.add_or_update_contact("a@example.com", MergeFields(), True)


@pytest.mark.asyncio
async def test_add_or_update_contact_network_failure_wraps_as_mailchimp_error(monkeypatch):
    _configure(monkeypatch)
    _install_fake_client(monkeypatch, exc=httpx.ConnectTimeout("timed out"))

    with pytest.raises(MailchimpError):
        await mailchimp_service.add_or_update_contact("a@example.com", MergeFields(), True)


@pytest.mark.asyncio
async def test_add_tags_to_contact_sends_active_tags(monkeypatch):
    _configure(monkeypatch)
    fake_client = _install_fake_client(monkeypatch, response=_FakeResponse(204))

    await mailchimp_service.add_tags_to_contact("a@example.com", ["LEAD", "AGENT_VOICE"])

    assert fake_client.last_kwargs["json"]["tags"] == [
        {"name": "LEAD", "status": "active"},
        {"name": "AGENT_VOICE", "status": "active"},
    ]


@pytest.mark.asyncio
async def test_add_tags_to_contact_noop_for_empty_tag_list(monkeypatch):
    _configure(monkeypatch)
    called = {"value": False}

    def _fail_if_called(**_):
        called["value"] = True

    monkeypatch.setattr(mailchimp_service.httpx, "AsyncClient", _fail_if_called)

    await mailchimp_service.add_tags_to_contact("a@example.com", [])

    assert called["value"] is False


@pytest.mark.asyncio
async def test_add_tags_to_contact_rate_limit(monkeypatch):
    _configure(monkeypatch)
    _install_fake_client(monkeypatch, response=_FakeResponse(429, text="rate limited"))

    with pytest.raises(MailchimpRateLimitError):
        await mailchimp_service.add_tags_to_contact("a@example.com", ["LEAD"])


def test_error_logging_never_includes_the_api_key(monkeypatch, caplog):
    _configure(monkeypatch)
    response = _FakeResponse(500, text="Internal Server Error")

    with caplog.at_level("WARNING"):
        with pytest.raises(MailchimpError):
            mailchimp_service._raise_for_response(response, "test_action")

    assert "test-secret-key" not in caplog.text
