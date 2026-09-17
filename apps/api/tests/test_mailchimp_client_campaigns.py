"""Unit tests for app/integrations/mailchimp_client.py's Campaigns API
methods (create_campaign/set_campaign_content/send_test_email/
send_campaign/schedule_campaign/get_campaign/get_campaign_report) -- added
for the Option A "Mailchimp is the system of record for the campaign
itself" architecture (see app/services/campaign_service.py's own module
docstring). Mocked at the httpx.AsyncClient boundary, same "mock at the
boundary, no real network call" idiom test_mailchimp_client.py's own
_FakeAsyncClient already uses for the OAuth/audience methods -- extended
here with `put` support (set_campaign_content is the first PUT call this
client makes).
"""

from datetime import datetime, timezone

import httpx
import pytest

from app.integrations import mailchimp_client
from app.integrations.mailchimp_client import MailchimpClient, MailchimpClientError, UNSUBSCRIBE_MERGE_TAG


class _FakeResponse:
    def __init__(self, status_code: int, json_data: dict | None = None, text: str = ""):
        self.status_code = status_code
        self._json_data = json_data or {}
        self.text = text

    def json(self):
        return self._json_data


class _FakeAsyncClient:
    def __init__(self, response=None, exc=None):
        self._response = response
        self._exc = exc
        self.last_url = None
        self.last_kwargs = None
        self.last_method = None

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc_info):
        return False

    async def _call(self, method, url, **kwargs):
        self.last_method = method
        self.last_url = url
        self.last_kwargs = kwargs
        if self._exc:
            raise self._exc
        return self._response

    async def get(self, url, **kwargs):
        return await self._call("get", url, **kwargs)

    async def post(self, url, **kwargs):
        return await self._call("post", url, **kwargs)

    async def put(self, url, **kwargs):
        return await self._call("put", url, **kwargs)


def _install_fake_client(monkeypatch, **kwargs):
    fake_client = _FakeAsyncClient(**kwargs)
    monkeypatch.setattr(mailchimp_client.httpx, "AsyncClient", lambda **_: fake_client)
    return fake_client


def _client() -> MailchimpClient:
    return MailchimpClient(access_token="tok", server_prefix="us21")


# --- create_campaign --------------------------------------------------


@pytest.mark.asyncio
async def test_create_campaign_posts_regular_type_and_list_id(monkeypatch):
    fake_client = _install_fake_client(monkeypatch, response=_FakeResponse(200, {"id": "camp1", "status": "save"}))

    data = await _client().create_campaign("aud1", "Hello", from_name="Acme", reply_to="owner@acme.com")

    assert data == {"id": "camp1", "status": "save", "emails_sent": 0, "send_time": None, "archive_url": None}
    assert fake_client.last_url == "https://us21.api.mailchimp.com/3.0/campaigns"
    payload = fake_client.last_kwargs["json"]
    assert payload["type"] == "regular"
    assert payload["recipients"] == {"list_id": "aud1"}
    assert payload["settings"]["subject_line"] == "Hello"
    assert payload["settings"]["from_name"] == "Acme"
    assert payload["settings"]["reply_to"] == "owner@acme.com"


@pytest.mark.asyncio
async def test_create_campaign_never_sends_a_from_email_field(monkeypatch):
    """Mailchimp's campaign settings object has no from_email field at
    all (verified against Mailchimp's own docs) -- this pins that this
    client never invents one, since doing so would silently do nothing on
    Mailchimp's side while looking like it worked."""
    fake_client = _install_fake_client(monkeypatch, response=_FakeResponse(200, {"id": "camp1", "status": "save"}))

    await _client().create_campaign("aud1", "Hello")

    assert "from_email" not in fake_client.last_kwargs["json"]["settings"]


@pytest.mark.asyncio
async def test_create_campaign_omits_optional_fields_when_not_given(monkeypatch):
    fake_client = _install_fake_client(monkeypatch, response=_FakeResponse(200, {"id": "camp1", "status": "save"}))

    await _client().create_campaign("aud1", "Hello")

    settings = fake_client.last_kwargs["json"]["settings"]
    assert "from_name" not in settings
    assert "reply_to" not in settings


@pytest.mark.asyncio
async def test_create_campaign_normalizes_response_missing_emails_sent(monkeypatch):
    """Mailchimp's create-campaign response is the same Campaign object
    shape get_campaign returns, but this pins that create_campaign's own
    return value is defensively normalized the same way (id/status/
    emails_sent/send_time/archive_url), not just passed through raw --
    callers (mailchimp_provider.py's _campaign_info) assume the normalized
    shape regardless of which of these two calls produced it."""
    _install_fake_client(monkeypatch, response=_FakeResponse(200, {"id": "camp1", "status": "save"}))

    data = await _client().create_campaign("aud1", "Hello")

    assert data["emails_sent"] == 0
    assert data["send_time"] is None
    assert data["archive_url"] is None


@pytest.mark.asyncio
async def test_create_campaign_http_error_raises(monkeypatch):
    _install_fake_client(monkeypatch, response=_FakeResponse(400, text="Invalid Resource"))

    with pytest.raises(MailchimpClientError):
        await _client().create_campaign("aud1", "Hello")


# --- set_campaign_content ----------------------------------------------


@pytest.mark.asyncio
async def test_set_campaign_content_puts_html_unchanged_when_unsub_tag_present(monkeypatch):
    fake_client = _install_fake_client(monkeypatch, response=_FakeResponse(200, {}))
    html = f'<p>Hi</p><a href="{UNSUBSCRIBE_MERGE_TAG}">unsub</a>'

    await _client().set_campaign_content("camp1", html)

    assert fake_client.last_method == "put"
    assert fake_client.last_url == "https://us21.api.mailchimp.com/3.0/campaigns/camp1/content"
    assert fake_client.last_kwargs["json"]["html"] == html


@pytest.mark.asyncio
async def test_set_campaign_content_appends_unsub_tag_when_missing(monkeypatch):
    fake_client = _install_fake_client(monkeypatch, response=_FakeResponse(200, {}))

    await _client().set_campaign_content("camp1", "<p>No unsubscribe link here</p>")

    sent_html = fake_client.last_kwargs["json"]["html"]
    assert UNSUBSCRIBE_MERGE_TAG in sent_html
    assert "<p>No unsubscribe link here</p>" in sent_html


@pytest.mark.asyncio
async def test_set_campaign_content_http_error_raises(monkeypatch):
    _install_fake_client(monkeypatch, response=_FakeResponse(404, text="not found"))

    with pytest.raises(MailchimpClientError):
        await _client().set_campaign_content("missing", "<p>hi</p>")


# --- send_test_email -----------------------------------------------------


@pytest.mark.asyncio
async def test_send_test_email_posts_addresses_and_html_send_type(monkeypatch):
    fake_client = _install_fake_client(monkeypatch, response=_FakeResponse(200, {}))

    await _client().send_test_email("camp1", ["a@example.com", "b@example.com"])

    assert fake_client.last_url == "https://us21.api.mailchimp.com/3.0/campaigns/camp1/actions/test"
    assert fake_client.last_kwargs["json"] == {"test_emails": ["a@example.com", "b@example.com"], "send_type": "html"}


@pytest.mark.asyncio
async def test_send_test_email_http_error_raises(monkeypatch):
    _install_fake_client(monkeypatch, response=_FakeResponse(400, text="bad request"))

    with pytest.raises(MailchimpClientError):
        await _client().send_test_email("camp1", ["a@example.com"])


# --- send_campaign / schedule_campaign -----------------------------------


@pytest.mark.asyncio
async def test_send_campaign_posts_to_actions_send_with_no_body(monkeypatch):
    fake_client = _install_fake_client(monkeypatch, response=_FakeResponse(204, {}))

    await _client().send_campaign("camp1")

    assert fake_client.last_url == "https://us21.api.mailchimp.com/3.0/campaigns/camp1/actions/send"
    assert "json" not in fake_client.last_kwargs


@pytest.mark.asyncio
async def test_send_campaign_http_error_raises(monkeypatch):
    _install_fake_client(monkeypatch, response=_FakeResponse(400, text="does not have a link to unsubscribe"))

    with pytest.raises(MailchimpClientError):
        await _client().send_campaign("camp1")


@pytest.mark.asyncio
async def test_schedule_campaign_sends_iso_utc_schedule_time(monkeypatch):
    fake_client = _install_fake_client(monkeypatch, response=_FakeResponse(204, {}))
    when = datetime(2026, 4, 1, 14, 0, 0, tzinfo=timezone.utc)

    await _client().schedule_campaign("camp1", when)

    assert fake_client.last_url == "https://us21.api.mailchimp.com/3.0/campaigns/camp1/actions/schedule"
    assert fake_client.last_kwargs["json"] == {"schedule_time": "2026-04-01T14:00:00+00:00"}


@pytest.mark.asyncio
async def test_schedule_campaign_http_error_raises(monkeypatch):
    _install_fake_client(monkeypatch, response=_FakeResponse(400, text="cannot be scheduled"))

    with pytest.raises(MailchimpClientError):
        await _client().schedule_campaign("camp1", datetime(2026, 4, 1, tzinfo=timezone.utc))


# --- get_campaign / get_campaign_report ----------------------------------


@pytest.mark.asyncio
async def test_get_campaign_returns_status_and_send_info(monkeypatch):
    _install_fake_client(
        monkeypatch,
        response=_FakeResponse(
            200,
            {"id": "camp1", "status": "sent", "emails_sent": 120, "send_time": "2026-04-01T14:00:00+00:00", "archive_url": "https://x"},
        ),
    )

    data = await _client().get_campaign("camp1")

    assert data == {
        "id": "camp1",
        "status": "sent",
        "emails_sent": 120,
        "send_time": "2026-04-01T14:00:00+00:00",
        "archive_url": "https://x",
    }


@pytest.mark.asyncio
async def test_get_campaign_defaults_missing_fields(monkeypatch):
    _install_fake_client(monkeypatch, response=_FakeResponse(200, {"id": "camp1", "status": "save"}))

    data = await _client().get_campaign("camp1")

    assert data["emails_sent"] == 0
    assert data["send_time"] is None
    assert data["archive_url"] is None


@pytest.mark.asyncio
async def test_get_campaign_http_error_raises(monkeypatch):
    _install_fake_client(monkeypatch, response=_FakeResponse(404, text="not found"))

    with pytest.raises(MailchimpClientError):
        await _client().get_campaign("missing")


@pytest.mark.asyncio
async def test_get_campaign_report_maps_nested_fields(monkeypatch):
    _install_fake_client(
        monkeypatch,
        response=_FakeResponse(
            200,
            {
                "emails_sent": 100,
                "opens": {"opens_total": 40, "unique_opens": 30, "open_rate": 30.0},
                "clicks": {"click_rate": 5.5},
                "unsubscribed": 2,
                "bounces": {"hard_bounces": 1, "soft_bounces": 3},
            },
        ),
    )

    report = await _client().get_campaign_report("camp1")

    assert report == {
        "emails_sent": 100,
        "opens_total": 40,
        "unique_opens": 30,
        "open_rate": 30.0,
        "click_rate": 5.5,
        "unsubscribed": 2,
        "hard_bounces": 1,
        "soft_bounces": 3,
    }


@pytest.mark.asyncio
async def test_get_campaign_report_defaults_missing_nested_objects(monkeypatch):
    _install_fake_client(monkeypatch, response=_FakeResponse(200, {"emails_sent": 5}))

    report = await _client().get_campaign_report("camp1")

    assert report["opens_total"] == 0
    assert report["click_rate"] == 0.0
    assert report["hard_bounces"] == 0


@pytest.mark.asyncio
async def test_get_campaign_report_http_error_raises(monkeypatch):
    """A campaign that hasn't sent yet -- Mailchimp 404s /reports for it."""
    _install_fake_client(monkeypatch, response=_FakeResponse(404, text="not found"))

    with pytest.raises(MailchimpClientError):
        await _client().get_campaign_report("not-sent-yet")


@pytest.mark.asyncio
async def test_campaign_network_failure_wraps_as_client_error(monkeypatch):
    _install_fake_client(monkeypatch, exc=httpx.ConnectTimeout("timed out"))

    with pytest.raises(MailchimpClientError):
        await _client().create_campaign("aud1", "Hello")
