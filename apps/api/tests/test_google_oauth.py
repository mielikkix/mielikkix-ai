"""SEO Audit & Optimization, Stage 12: real per-tenant Google Analytics +
Search Console OAuth (app/api/google_oauth.py). No test here makes a real
call to Google -- google_auth_oauthlib.flow.Flow is mocked at the
boundary (via google_oauth._build_flow), same convention
test_calendar_oauth.py already uses for the structurally identical
Calendar OAuth flow.
"""

import hashlib
import hmac
import time
from unittest.mock import MagicMock

from app.api import google_oauth
from app.core.config import settings
from app.core.encryption import decrypt, encrypt
from app.models.seo_google_connection import SeoGoogleConnection


def _entitle(business, grant_agent):
    grant_agent(business["business_id"], "seo_audit_optimization")


def _expired_state(business_id: str) -> str:
    old_timestamp = int(time.time()) - google_oauth._STATE_TTL_SECONDS - 10
    payload = f"{business_id}:{old_timestamp}"
    signature = hmac.new(settings.secret_key.encode(), payload.encode(), hashlib.sha256).hexdigest()
    return f"{payload}:{signature}"


def test_sign_and_verify_state_round_trips():
    state = google_oauth._sign_state("some-business-id")
    assert google_oauth._verify_state(state) == "some-business-id"


def test_verify_state_rejects_tampered_signature():
    state = google_oauth._sign_state("some-business-id")
    business_id, timestamp, _signature = state.split(":")
    tampered = f"{business_id}:{timestamp}:0"
    try:
        google_oauth._verify_state(tampered)
        assert False, "expected ValueError"
    except ValueError:
        pass


def test_verify_state_rejects_expired_state():
    try:
        google_oauth._verify_state(_expired_state("some-business-id"))
        assert False, "expected ValueError"
    except ValueError:
        pass


def test_authorize_requires_login(client):
    resp = client.get("/api/businesses/me/google/authorize", follow_redirects=False)
    assert resp.status_code == 401


def test_authorize_requires_agent_access(client, business):
    resp = client.get("/api/businesses/me/google/authorize", headers=business["headers"], follow_redirects=False)
    assert resp.status_code == 403


def test_authorize_503_when_oauth_client_not_configured(client, business, grant_agent, monkeypatch):
    _entitle(business, grant_agent)
    monkeypatch.setattr(settings, "google_analytics_oauth_client_id", "")
    monkeypatch.setattr(settings, "google_analytics_oauth_client_secret", "")

    resp = client.get("/api/businesses/me/google/authorize", headers=business["headers"], follow_redirects=False)
    assert resp.status_code == 503


def test_authorize_redirects_to_google_consent_screen(client, business, grant_agent, monkeypatch):
    _entitle(business, grant_agent)
    monkeypatch.setattr(settings, "google_analytics_oauth_client_id", "test-client-id")
    monkeypatch.setattr(settings, "google_analytics_oauth_client_secret", "test-client-secret")
    fake_flow = MagicMock()
    fake_flow.authorization_url.return_value = ("https://accounts.google.com/o/oauth2/auth?fake=1", "unused")
    monkeypatch.setattr(google_oauth, "_build_flow", lambda: fake_flow)

    resp = client.get("/api/businesses/me/google/authorize", headers=business["headers"], follow_redirects=False)

    assert resp.status_code in (302, 307)
    assert resp.headers["location"] == "https://accounts.google.com/o/oauth2/auth?fake=1"
    _, call_kwargs = fake_flow.authorization_url.call_args
    assert call_kwargs["access_type"] == "offline"
    assert call_kwargs["prompt"] == "consent"
    assert google_oauth._verify_state(call_kwargs["state"]) == business["business_id"]


def test_callback_missing_code_redirects_to_error(client):
    resp = client.get("/api/businesses/me/google/callback", follow_redirects=False)
    assert resp.status_code in (302, 307)
    assert "google=error" in resp.headers["location"]


def test_callback_invalid_state_redirects_to_error(client):
    resp = client.get(
        "/api/businesses/me/google/callback",
        params={"code": "abc", "state": "not-a-valid-state"},
        follow_redirects=False,
    )
    assert resp.status_code in (302, 307)
    assert "google=error" in resp.headers["location"]


def test_callback_no_refresh_token_redirects_to_error(client, business, monkeypatch):
    state = google_oauth._sign_state(business["business_id"])
    fake_credentials = MagicMock(refresh_token=None)
    fake_flow = MagicMock()
    fake_flow.credentials = fake_credentials
    monkeypatch.setattr(google_oauth, "_build_flow", lambda: fake_flow)

    resp = client.get(
        "/api/businesses/me/google/callback",
        params={"code": "auth-code", "state": state},
        follow_redirects=False,
    )
    assert "google=error" in resp.headers["location"]


def test_callback_success_creates_connection(client, business, db_session, monkeypatch):
    state = google_oauth._sign_state(business["business_id"])
    fake_credentials = MagicMock(refresh_token="real-refresh-token")
    fake_flow = MagicMock()
    fake_flow.credentials = fake_credentials
    monkeypatch.setattr(google_oauth, "_build_flow", lambda: fake_flow)
    monkeypatch.setattr(google_oauth, "_fetch_google_account_email", lambda credentials: "owner@example.com")

    resp = client.get(
        "/api/businesses/me/google/callback",
        params={"code": "auth-code", "state": state},
        follow_redirects=False,
    )

    assert resp.status_code in (302, 307)
    assert "google=connected" in resp.headers["location"]

    connection = (
        db_session.query(SeoGoogleConnection)
        .filter(SeoGoogleConnection.business_id == business["business_id"])
        .first()
    )
    assert connection is not None
    assert connection.google_account_email == "owner@example.com"
    assert decrypt(connection.refresh_token_encrypted) == "real-refresh-token"
    # Connecting alone doesn't configure anything to read from yet.
    assert connection.analytics_property_id is None
    assert connection.search_console_site_url is None


def test_status_when_not_connected(client, business):
    resp = client.get("/api/businesses/me/google/status", headers=business["headers"])
    assert resp.status_code == 200
    assert resp.json() == {"connected": False}


def test_status_when_connected(client, business, db_session):
    db_session.add(
        SeoGoogleConnection(
            business_id=business["business_id"],
            refresh_token_encrypted=encrypt("tenant-token"),
            google_account_email="owner@example.com",
        )
    )
    db_session.commit()

    resp = client.get("/api/businesses/me/google/status", headers=business["headers"])

    body = resp.json()
    assert body["connected"] is True
    assert body["google_account_email"] == "owner@example.com"
    assert body["analytics_property_id"] is None


def test_update_config_sets_property_and_site(client, business, db_session):
    db_session.add(SeoGoogleConnection(business_id=business["business_id"], refresh_token_encrypted=encrypt("t")))
    db_session.commit()

    resp = client.patch(
        "/api/businesses/me/google/config",
        json={"analytics_property_id": "properties/123", "search_console_site_url": "https://greenleaf.test/"},
        headers=business["headers"],
    )

    assert resp.status_code == 200
    body = resp.json()
    assert body["analytics_property_id"] == "properties/123"
    assert body["search_console_site_url"] == "https://greenleaf.test/"


def test_update_config_404s_when_not_connected(client, business):
    resp = client.patch(
        "/api/businesses/me/google/config",
        json={"analytics_property_id": "properties/123"},
        headers=business["headers"],
    )
    assert resp.status_code == 404


def test_disconnect_removes_connection(client, business, db_session):
    db_session.add(SeoGoogleConnection(business_id=business["business_id"], refresh_token_encrypted=encrypt("t")))
    db_session.commit()

    resp = client.delete("/api/businesses/me/google", headers=business["headers"])

    assert resp.status_code == 200
    assert resp.json() == {"connected": False}
    assert db_session.query(SeoGoogleConnection).filter(
        SeoGoogleConnection.business_id == business["business_id"]
    ).count() == 0


def test_google_endpoints_are_tenant_scoped(client, business, signup, db_session):
    other = signup()
    db_session.add(SeoGoogleConnection(business_id=other["business_id"], refresh_token_encrypted=encrypt("other-token")))
    db_session.commit()

    resp = client.get("/api/businesses/me/google/status", headers=business["headers"])
    assert resp.json() == {"connected": False}

    client.delete("/api/businesses/me/google", headers=business["headers"])
    assert db_session.query(SeoGoogleConnection).filter(
        SeoGoogleConnection.business_id == other["business_id"]
    ).count() == 1
