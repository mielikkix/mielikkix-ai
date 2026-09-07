"""Email Marketing Agent: real per-tenant Mailchimp OAuth
(app/api/mailchimp_oauth.py). No test here makes a real call to Mailchimp --
exchange_code_for_token/fetch_metadata are mocked at the module-function
boundary and MailchimpClient is mocked at the class boundary, same
convention test_review_oauth.py uses for its own Google-based OAuth
(_build_flow / GoogleReviewsClient).

Deliberately NOT touching app/services/mailchimp_service.py or its own
test_mailchimp_service.py -- that is Mielikkix's own single-account lead
sync, a completely separate system from the per-tenant OAuth tested here.
"""

import hashlib
import hmac
import time
from unittest.mock import AsyncMock, MagicMock

import httpx
import pytest

from app.api import mailchimp_oauth
from app.core.config import settings
from app.core.encryption import decrypt, encrypt
from app.models.mailchimp_connection import MailchimpConnection


def _expired_state(business_id: str) -> str:
    old_timestamp = int(time.time()) - mailchimp_oauth._STATE_TTL_SECONDS - 10
    payload = f"{business_id}:{old_timestamp}"
    signature = hmac.new(settings.secret_key.encode(), payload.encode(), hashlib.sha256).hexdigest()
    return f"{payload}:{signature}"


def _configure_oauth(monkeypatch):
    monkeypatch.setattr(settings, "mailchimp_oauth_client_id", "test-client-id")
    monkeypatch.setattr(settings, "mailchimp_oauth_client_secret", "test-client-secret")


def _patch_token_exchange(monkeypatch, access_token="real-access-token", exc=None):
    mock = AsyncMock(side_effect=exc) if exc else AsyncMock(return_value=access_token)
    monkeypatch.setattr(mailchimp_oauth, "exchange_code_for_token", mock)
    return mock


def _patch_metadata(monkeypatch, metadata=None, exc=None):
    default = {"dc": "us21", "accountname": "Test Account", "login": {"email": "owner@example.com"}}
    mock = AsyncMock(side_effect=exc) if exc else AsyncMock(return_value=metadata or default)
    monkeypatch.setattr(mailchimp_oauth, "fetch_metadata", mock)
    return mock


def _patch_client(monkeypatch, audiences=None, exc=None):
    fake_client = MagicMock()
    if exc:
        fake_client.list_audiences = AsyncMock(side_effect=exc)
    else:
        fake_client.list_audiences = AsyncMock(return_value=audiences if audiences is not None else [])
    monkeypatch.setattr(mailchimp_oauth, "MailchimpClient", MagicMock(return_value=fake_client))
    return fake_client


# --- state signing --------------------------------------------------------


def test_sign_and_verify_state_round_trips():
    state = mailchimp_oauth._sign_state("some-business-id")

    assert mailchimp_oauth._verify_state(state) == "some-business-id"


def test_verify_state_rejects_tampered_signature():
    state = mailchimp_oauth._sign_state("some-business-id")
    business_id, timestamp, _signature = state.split(":")
    tampered = f"{business_id}:{timestamp}:0"

    with pytest.raises(ValueError):
        mailchimp_oauth._verify_state(tampered)


def test_verify_state_rejects_expired_state():
    with pytest.raises(ValueError):
        mailchimp_oauth._verify_state(_expired_state("some-business-id"))


def test_verify_state_rejects_malformed_state():
    with pytest.raises(ValueError):
        mailchimp_oauth._verify_state("not-a-valid-state-at-all")


# --- /authorize -------------------------------------------------------------


def test_authorize_requires_login(client):
    resp = client.get("/api/businesses/me/mailchimp/authorize", follow_redirects=False)

    assert resp.status_code == 401


def test_authorize_requires_email_marketing_enabled_plan(client, business):
    # Free plan (business fixture's default) doesn't include email_marketing_enabled.
    resp = client.get("/api/businesses/me/mailchimp/authorize", headers=business["headers"], follow_redirects=False)

    assert resp.status_code == 403


def test_authorize_503_when_oauth_client_not_configured(client, business, set_plan, monkeypatch):
    set_plan(business["business_id"], "business")
    monkeypatch.setattr(settings, "mailchimp_oauth_client_id", "")
    monkeypatch.setattr(settings, "mailchimp_oauth_client_secret", "")

    resp = client.get("/api/businesses/me/mailchimp/authorize", headers=business["headers"], follow_redirects=False)

    assert resp.status_code == 503


def test_authorize_redirects_to_mailchimp_consent_screen(client, business, set_plan, monkeypatch):
    set_plan(business["business_id"], "business")
    _configure_oauth(monkeypatch)

    resp = client.get("/api/businesses/me/mailchimp/authorize", headers=business["headers"], follow_redirects=False)

    assert resp.status_code in (302, 307)
    location = resp.headers["location"]
    assert location.startswith("https://login.mailchimp.com/oauth2/authorize?")
    parsed = httpx.URL(location)
    assert parsed.params["response_type"] == "code"
    assert parsed.params["client_id"] == "test-client-id"
    assert mailchimp_oauth._verify_state(parsed.params["state"]) == business["business_id"]


# --- /callback ----------------------------------------------------------


def test_callback_missing_code_redirects_to_error(client):
    resp = client.get("/api/businesses/me/mailchimp/callback", follow_redirects=False)

    assert resp.status_code in (302, 307)
    assert "mailchimp=error" in resp.headers["location"]


def test_callback_denied_authorization_redirects_to_error(client):
    resp = client.get(
        "/api/businesses/me/mailchimp/callback", params={"error": "access_denied"}, follow_redirects=False
    )

    assert "mailchimp=error" in resp.headers["location"]


def test_callback_invalid_state_redirects_to_error(client):
    resp = client.get(
        "/api/businesses/me/mailchimp/callback", params={"code": "abc", "state": "garbage"}, follow_redirects=False
    )

    assert "mailchimp=error" in resp.headers["location"]


def test_callback_expired_state_redirects_to_error(client, business):
    resp = client.get(
        "/api/businesses/me/mailchimp/callback",
        params={"code": "abc", "state": _expired_state(business["business_id"])},
        follow_redirects=False,
    )

    assert "mailchimp=error" in resp.headers["location"]


def test_callback_token_exchange_failure_redirects_to_error(client, business, monkeypatch):
    from app.integrations.mailchimp_client import MailchimpClientError

    state = mailchimp_oauth._sign_state(business["business_id"])
    _patch_token_exchange(monkeypatch, exc=MailchimpClientError("bad code"))

    resp = client.get(
        "/api/businesses/me/mailchimp/callback", params={"code": "abc", "state": state}, follow_redirects=False
    )

    assert "mailchimp=error" in resp.headers["location"]


def test_callback_metadata_failure_redirects_to_error(client, business, monkeypatch):
    from app.integrations.mailchimp_client import MailchimpClientError

    state = mailchimp_oauth._sign_state(business["business_id"])
    _patch_token_exchange(monkeypatch)
    _patch_metadata(monkeypatch, exc=MailchimpClientError("no dc"))

    resp = client.get(
        "/api/businesses/me/mailchimp/callback", params={"code": "abc", "state": state}, follow_redirects=False
    )

    assert "mailchimp=error" in resp.headers["location"]


def test_callback_success_creates_connection(client, business, db_session, monkeypatch):
    state = mailchimp_oauth._sign_state(business["business_id"])
    _patch_token_exchange(monkeypatch, access_token="real-access-token")
    _patch_metadata(monkeypatch, metadata={"dc": "us19", "accountname": "Acme Inc", "login": {"email": "a@acme.com"}})

    resp = client.get(
        "/api/businesses/me/mailchimp/callback", params={"code": "abc", "state": state}, follow_redirects=False
    )

    assert "mailchimp=connected" in resp.headers["location"]
    connection = (
        db_session.query(MailchimpConnection).filter(MailchimpConnection.business_id == business["business_id"]).first()
    )
    assert connection is not None
    assert connection.server_prefix == "us19"
    assert connection.account_name == "Acme Inc"
    assert connection.login_email == "a@acme.com"
    assert decrypt(connection.access_token_encrypted) == "real-access-token"


def test_callback_reconnect_overwrites_existing_connection(client, business, db_session, monkeypatch):
    """A business connecting a second time (e.g. after disconnecting, or
    re-authorizing a different Mailchimp account) updates the SAME row
    rather than creating a duplicate -- unique business_id enforces this,
    but the upsert logic must actually find and reuse the existing row."""
    state = mailchimp_oauth._sign_state(business["business_id"])
    _patch_token_exchange(monkeypatch, access_token="first-token")
    _patch_metadata(monkeypatch, metadata={"dc": "us1", "accountname": "First", "login": {"email": "first@x.com"}})
    client.get("/api/businesses/me/mailchimp/callback", params={"code": "abc", "state": state}, follow_redirects=False)

    state2 = mailchimp_oauth._sign_state(business["business_id"])
    _patch_token_exchange(monkeypatch, access_token="second-token")
    _patch_metadata(monkeypatch, metadata={"dc": "us2", "accountname": "Second", "login": {"email": "second@x.com"}})
    client.get("/api/businesses/me/mailchimp/callback", params={"code": "def", "state": state2}, follow_redirects=False)

    connections = (
        db_session.query(MailchimpConnection).filter(MailchimpConnection.business_id == business["business_id"]).all()
    )
    assert len(connections) == 1
    assert connections[0].server_prefix == "us2"
    assert decrypt(connections[0].access_token_encrypted) == "second-token"


# --- /status --------------------------------------------------------------


def test_status_when_not_connected(client, business):
    resp = client.get("/api/businesses/me/mailchimp/status", headers=business["headers"])

    assert resp.status_code == 200
    assert resp.json() == {"connected": False, "configured": False}


def test_status_reports_configured_when_oauth_client_is_set(client, business, monkeypatch):
    _configure_oauth(monkeypatch)

    resp = client.get("/api/businesses/me/mailchimp/status", headers=business["headers"])

    assert resp.json()["configured"] is True


def test_status_when_connected(client, business, db_session):
    connection = MailchimpConnection(
        business_id=business["business_id"],
        access_token_encrypted=encrypt("tok"),
        server_prefix="us21",
        account_name="Acme Inc",
        login_email="owner@acme.com",
        audience_id="abc123",
        audience_name="Main List",
    )
    db_session.add(connection)
    db_session.commit()

    resp = client.get("/api/businesses/me/mailchimp/status", headers=business["headers"])

    body = resp.json()
    assert body["connected"] is True
    assert body["account_name"] == "Acme Inc"
    assert body["login_email"] == "owner@acme.com"
    assert body["audience_id"] == "abc123"
    assert body["audience_name"] == "Main List"


def test_status_never_exposes_the_access_token(client, business, db_session):
    connection = MailchimpConnection(
        business_id=business["business_id"], access_token_encrypted=encrypt("super-secret-token"), server_prefix="us21"
    )
    db_session.add(connection)
    db_session.commit()

    resp = client.get("/api/businesses/me/mailchimp/status", headers=business["headers"])

    assert "super-secret-token" not in resp.text
    assert "access_token" not in resp.json()
    assert "access_token_encrypted" not in resp.json()


# --- /audiences -------------------------------------------------------------


def test_list_audiences_requires_existing_connection(client, business):
    resp = client.get("/api/businesses/me/mailchimp/audiences", headers=business["headers"])

    assert resp.status_code == 404


def test_list_audiences_returns_multiple(client, business, db_session, monkeypatch):
    connection = MailchimpConnection(
        business_id=business["business_id"], access_token_encrypted=encrypt("tok"), server_prefix="us21"
    )
    db_session.add(connection)
    db_session.commit()
    _patch_client(
        monkeypatch,
        audiences=[
            {"id": "list-1", "name": "Newsletter", "member_count": 120},
            {"id": "list-2", "name": "VIP Customers", "member_count": 8},
        ],
    )

    resp = client.get("/api/businesses/me/mailchimp/audiences", headers=business["headers"])

    assert resp.status_code == 200
    assert resp.json() == [
        {"id": "list-1", "name": "Newsletter", "member_count": 120},
        {"id": "list-2", "name": "VIP Customers", "member_count": 8},
    ]


def test_list_audiences_handles_zero_audiences_cleanly(client, business, db_session, monkeypatch):
    connection = MailchimpConnection(
        business_id=business["business_id"], access_token_encrypted=encrypt("tok"), server_prefix="us21"
    )
    db_session.add(connection)
    db_session.commit()
    _patch_client(monkeypatch, audiences=[])

    resp = client.get("/api/businesses/me/mailchimp/audiences", headers=business["headers"])

    assert resp.status_code == 200
    assert resp.json() == []


def test_list_audiences_upstream_failure_returns_clean_502(client, business, db_session, monkeypatch):
    from app.integrations.mailchimp_client import MailchimpClientError

    connection = MailchimpConnection(
        business_id=business["business_id"], access_token_encrypted=encrypt("tok"), server_prefix="us21"
    )
    db_session.add(connection)
    db_session.commit()
    _patch_client(monkeypatch, exc=MailchimpClientError("HTTP 500"))

    resp = client.get("/api/businesses/me/mailchimp/audiences", headers=business["headers"])

    assert resp.status_code == 502
    assert "HTTP 500" not in resp.text  # no raw upstream error text leaked
    assert "access_token" not in resp.text


# --- /select-audience -------------------------------------------------------


def test_select_audience_requires_existing_connection(client, business):
    resp = client.post(
        "/api/businesses/me/mailchimp/select-audience",
        json={"audience_id": "list-1", "name": "Newsletter"},
        headers=business["headers"],
    )

    assert resp.status_code == 404


def test_select_audience_persists_selection(client, business, db_session):
    connection = MailchimpConnection(
        business_id=business["business_id"], access_token_encrypted=encrypt("tok"), server_prefix="us21"
    )
    db_session.add(connection)
    db_session.commit()

    resp = client.post(
        "/api/businesses/me/mailchimp/select-audience",
        json={"audience_id": "list-1", "name": "Newsletter"},
        headers=business["headers"],
    )

    assert resp.status_code == 200
    db_session.refresh(connection)
    assert connection.audience_id == "list-1"
    assert connection.audience_name == "Newsletter"


def test_select_audience_can_change_a_previous_selection(client, business, db_session):
    connection = MailchimpConnection(
        business_id=business["business_id"],
        access_token_encrypted=encrypt("tok"),
        server_prefix="us21",
        audience_id="list-1",
        audience_name="Newsletter",
    )
    db_session.add(connection)
    db_session.commit()

    resp = client.post(
        "/api/businesses/me/mailchimp/select-audience",
        json={"audience_id": "list-2", "name": "VIP Customers"},
        headers=business["headers"],
    )

    assert resp.status_code == 200
    db_session.refresh(connection)
    assert connection.audience_id == "list-2"
    assert connection.audience_name == "VIP Customers"


# --- disconnect / reconnect -------------------------------------------------


def test_disconnect_removes_connection(client, business, db_session):
    connection = MailchimpConnection(
        business_id=business["business_id"], access_token_encrypted=encrypt("tok"), server_prefix="us21"
    )
    db_session.add(connection)
    db_session.commit()

    resp = client.delete("/api/businesses/me/mailchimp", headers=business["headers"])

    assert resp.status_code == 200
    assert (
        db_session.query(MailchimpConnection).filter(MailchimpConnection.business_id == business["business_id"]).first()
        is None
    )


def test_reconnect_after_disconnect_works(client, business, db_session, monkeypatch):
    connection = MailchimpConnection(
        business_id=business["business_id"], access_token_encrypted=encrypt("tok"), server_prefix="us21"
    )
    db_session.add(connection)
    db_session.commit()
    client.delete("/api/businesses/me/mailchimp", headers=business["headers"])

    state = mailchimp_oauth._sign_state(business["business_id"])
    _patch_token_exchange(monkeypatch, access_token="fresh-token")
    _patch_metadata(monkeypatch, metadata={"dc": "us5", "accountname": "New", "login": {"email": "n@x.com"}})
    resp = client.get(
        "/api/businesses/me/mailchimp/callback", params={"code": "abc", "state": state}, follow_redirects=False
    )

    assert "mailchimp=connected" in resp.headers["location"]
    new_connection = (
        db_session.query(MailchimpConnection).filter(MailchimpConnection.business_id == business["business_id"]).first()
    )
    assert new_connection is not None
    assert decrypt(new_connection.access_token_encrypted) == "fresh-token"


# --- tenant isolation ---------------------------------------------------


def test_mailchimp_status_is_tenant_scoped(client, business, signup, db_session):
    other = signup()
    connection = MailchimpConnection(
        business_id=other["business_id"], access_token_encrypted=encrypt("tok"), server_prefix="us21",
        audience_id="list-1", audience_name="Other's Newsletter",
    )
    db_session.add(connection)
    db_session.commit()

    resp = client.get("/api/businesses/me/mailchimp/status", headers=business["headers"])

    assert resp.json() == {"connected": False, "configured": False}


def test_tenant_cannot_select_audience_on_another_tenants_connection(client, business, signup, db_session):
    other = signup()
    connection = MailchimpConnection(
        business_id=other["business_id"], access_token_encrypted=encrypt("tok"), server_prefix="us21"
    )
    db_session.add(connection)
    db_session.commit()

    resp = client.post(
        "/api/businesses/me/mailchimp/select-audience",
        json={"audience_id": "list-1", "name": "Newsletter"},
        headers=business["headers"],
    )

    assert resp.status_code == 404
    db_session.refresh(connection)
    assert connection.audience_id is None


def test_tenant_cannot_disconnect_another_tenants_connection(client, business, signup, db_session):
    other = signup()
    connection = MailchimpConnection(
        business_id=other["business_id"], access_token_encrypted=encrypt("tok"), server_prefix="us21"
    )
    db_session.add(connection)
    db_session.commit()

    resp = client.delete("/api/businesses/me/mailchimp", headers=business["headers"])

    assert resp.status_code == 200
    assert (
        db_session.query(MailchimpConnection).filter(MailchimpConnection.business_id == other["business_id"]).first()
        is not None
    )


# --- unauthenticated access --------------------------------------------


@pytest.mark.parametrize(
    "method,path",
    [
        ("get", "/api/businesses/me/mailchimp/status"),
        ("get", "/api/businesses/me/mailchimp/audiences"),
        ("post", "/api/businesses/me/mailchimp/select-audience"),
        ("delete", "/api/businesses/me/mailchimp"),
    ],
)
def test_every_route_requires_authentication(client, method, path):
    resp = getattr(client, method)(path)

    assert resp.status_code == 401
