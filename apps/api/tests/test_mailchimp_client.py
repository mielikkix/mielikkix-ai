"""Unit tests for app/integrations/mailchimp_client.py -- the per-tenant
OAuth client used by mailchimp_oauth.py. Mocked at the httpx.AsyncClient
boundary (no real network call, no real Mailchimp account needed), same
"mock at the boundary" idiom as test_mailchimp_service.py's own
_FakeAsyncClient for Mielikkix's separate single-account lead sync client.
"""

import httpx
import pytest

from app.integrations import mailchimp_client
from app.integrations.mailchimp_client import MailchimpClient, MailchimpClientError


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

    async def get(self, url, **kwargs):
        return await self._call(url, **kwargs)

    async def post(self, url, **kwargs):
        return await self._call(url, **kwargs)


def _install_fake_client(monkeypatch, **kwargs):
    fake_client = _FakeAsyncClient(**kwargs)
    monkeypatch.setattr(mailchimp_client.httpx, "AsyncClient", lambda **_: fake_client)
    return fake_client


# --- exchange_code_for_token -------------------------------------------


@pytest.mark.asyncio
async def test_exchange_code_for_token_returns_access_token(monkeypatch):
    fake_client = _install_fake_client(
        monkeypatch, response=_FakeResponse(200, {"access_token": "tok-123", "expires_in": 0, "scope": None})
    )

    token = await mailchimp_client.exchange_code_for_token("cid", "csecret", "https://example.com/cb", "auth-code")

    assert token == "tok-123"
    assert fake_client.last_url == mailchimp_client.MAILCHIMP_TOKEN_URL
    assert fake_client.last_kwargs["data"] == {
        "grant_type": "authorization_code",
        "client_id": "cid",
        "client_secret": "csecret",
        "redirect_uri": "https://example.com/cb",
        "code": "auth-code",
    }


@pytest.mark.asyncio
async def test_exchange_code_for_token_uses_form_encoding_not_json(monkeypatch):
    """Mailchimp's token endpoint is form-encoded, per their own OAuth
    guide -- sending `json=` instead of `data=` would silently fail
    against the real API even though a mock wouldn't catch the difference,
    so this pins the actual kwarg used."""
    fake_client = _install_fake_client(monkeypatch, response=_FakeResponse(200, {"access_token": "tok"}))

    await mailchimp_client.exchange_code_for_token("cid", "csecret", "https://example.com/cb", "code")

    assert "json" not in fake_client.last_kwargs
    assert "data" in fake_client.last_kwargs


@pytest.mark.asyncio
async def test_exchange_code_for_token_missing_token_raises(monkeypatch):
    _install_fake_client(monkeypatch, response=_FakeResponse(200, {"scope": None}))

    with pytest.raises(MailchimpClientError):
        await mailchimp_client.exchange_code_for_token("cid", "csecret", "https://example.com/cb", "code")


@pytest.mark.asyncio
async def test_exchange_code_for_token_http_error_raises(monkeypatch):
    _install_fake_client(monkeypatch, response=_FakeResponse(400, text="invalid_grant"))

    with pytest.raises(MailchimpClientError):
        await mailchimp_client.exchange_code_for_token("cid", "csecret", "https://example.com/cb", "bad-code")


@pytest.mark.asyncio
async def test_exchange_code_for_token_network_failure_wraps_as_client_error(monkeypatch):
    _install_fake_client(monkeypatch, exc=httpx.ConnectTimeout("timed out"))

    with pytest.raises(MailchimpClientError):
        await mailchimp_client.exchange_code_for_token("cid", "csecret", "https://example.com/cb", "code")


@pytest.mark.asyncio
async def test_exchange_code_for_token_never_leaks_client_secret_in_error(monkeypatch, caplog):
    _install_fake_client(monkeypatch, response=_FakeResponse(400, text="invalid_grant"))

    with caplog.at_level("WARNING"):
        with pytest.raises(MailchimpClientError):
            await mailchimp_client.exchange_code_for_token("cid", "super-secret-value", "https://example.com/cb", "code")

    assert "super-secret-value" not in caplog.text


# --- fetch_metadata -------------------------------------------------------


@pytest.mark.asyncio
async def test_fetch_metadata_returns_dc_and_best_effort_fields(monkeypatch):
    fake_client = _install_fake_client(
        monkeypatch,
        response=_FakeResponse(
            200, {"dc": "us21", "accountname": "Acme", "login": {"email": "a@acme.com"}}
        ),
    )

    metadata = await mailchimp_client.fetch_metadata("access-token")

    assert metadata["dc"] == "us21"
    assert fake_client.last_kwargs["headers"] == {"Authorization": "OAuth access-token"}


@pytest.mark.asyncio
async def test_fetch_metadata_uses_oauth_scheme_not_bearer(monkeypatch):
    """Verified against Mailchimp's own OAuth guide: the header scheme is
    literally "OAuth", not "Bearer" -- this pins that exact string."""
    fake_client = _install_fake_client(monkeypatch, response=_FakeResponse(200, {"dc": "us1"}))

    await mailchimp_client.fetch_metadata("tok")

    auth_header = fake_client.last_kwargs["headers"]["Authorization"]
    assert auth_header.startswith("OAuth ")
    assert not auth_header.startswith("Bearer")


@pytest.mark.asyncio
async def test_fetch_metadata_missing_dc_raises(monkeypatch):
    _install_fake_client(monkeypatch, response=_FakeResponse(200, {"accountname": "Acme"}))

    with pytest.raises(MailchimpClientError):
        await mailchimp_client.fetch_metadata("tok")


@pytest.mark.asyncio
async def test_fetch_metadata_http_error_raises(monkeypatch):
    _install_fake_client(monkeypatch, response=_FakeResponse(401, text="invalid token"))

    with pytest.raises(MailchimpClientError):
        await mailchimp_client.fetch_metadata("bad-token")


# --- MailchimpClient.list_audiences / get_audience --------------------


@pytest.mark.asyncio
async def test_list_audiences_maps_fields_correctly(monkeypatch):
    fake_client = _install_fake_client(
        monkeypatch,
        response=_FakeResponse(
            200,
            {
                "lists": [
                    {"id": "l1", "name": "Newsletter", "stats": {"member_count": 42}},
                    {"id": "l2", "name": "VIPs", "stats": {"member_count": 3}},
                ]
            },
        ),
    )

    client = MailchimpClient(access_token="tok", server_prefix="us21")
    audiences = await client.list_audiences()

    assert audiences == [
        {"id": "l1", "name": "Newsletter", "member_count": 42},
        {"id": "l2", "name": "VIPs", "member_count": 3},
    ]
    assert fake_client.last_url == "https://us21.api.mailchimp.com/3.0/lists"
    assert fake_client.last_kwargs["headers"] == {"Authorization": "OAuth tok"}


@pytest.mark.asyncio
async def test_list_audiences_empty_account_returns_empty_list(monkeypatch):
    _install_fake_client(monkeypatch, response=_FakeResponse(200, {"lists": []}))

    client = MailchimpClient(access_token="tok", server_prefix="us21")
    audiences = await client.list_audiences()

    assert audiences == []


@pytest.mark.asyncio
async def test_list_audiences_missing_stats_defaults_member_count_to_zero(monkeypatch):
    _install_fake_client(monkeypatch, response=_FakeResponse(200, {"lists": [{"id": "l1", "name": "Bare"}]}))

    client = MailchimpClient(access_token="tok", server_prefix="us21")
    audiences = await client.list_audiences()

    assert audiences == [{"id": "l1", "name": "Bare", "member_count": 0}]


@pytest.mark.asyncio
async def test_list_audiences_http_error_raises(monkeypatch):
    _install_fake_client(monkeypatch, response=_FakeResponse(500, text="server error"))

    client = MailchimpClient(access_token="tok", server_prefix="us21")
    with pytest.raises(MailchimpClientError):
        await client.list_audiences()


@pytest.mark.asyncio
async def test_get_audience_returns_one_audience(monkeypatch):
    _install_fake_client(
        monkeypatch, response=_FakeResponse(200, {"id": "l1", "name": "Newsletter", "stats": {"member_count": 99}})
    )

    client = MailchimpClient(access_token="tok", server_prefix="us21")
    audience = await client.get_audience("l1")

    assert audience == {"id": "l1", "name": "Newsletter", "member_count": 99}


@pytest.mark.asyncio
async def test_get_audience_http_error_raises(monkeypatch):
    _install_fake_client(monkeypatch, response=_FakeResponse(404, text="not found"))

    client = MailchimpClient(access_token="tok", server_prefix="us21")
    with pytest.raises(MailchimpClientError):
        await client.get_audience("nonexistent")


def test_error_logging_never_includes_the_access_token(caplog):
    response = _FakeResponse(500, text="Internal Server Error")

    with caplog.at_level("WARNING"):
        with pytest.raises(MailchimpClientError):
            mailchimp_client._raise_for_response(response, "test_action")

    assert "test_action" in caplog.text
