"""Booking Assistant Phase 5: real per-tenant Google Calendar OAuth
(app/api/calendar_oauth.py). No test here makes a real call to Google --
google_auth_oauthlib.flow.Flow is mocked at the boundary (via
calendar_oauth._build_flow), same convention test_google_calendar_client.py
already uses for the Google Calendar API client itself.
"""

import hashlib
import hmac
import time
from unittest.mock import MagicMock

from app.api import calendar_oauth
from app.core.config import settings
from app.core.encryption import decrypt
from app.models.calendar_connection import CalendarConnection


def _expired_state(business_id: str) -> str:
    old_timestamp = int(time.time()) - calendar_oauth._STATE_TTL_SECONDS - 10
    payload = f"{business_id}:{old_timestamp}"
    signature = hmac.new(settings.secret_key.encode(), payload.encode(), hashlib.sha256).hexdigest()
    return f"{payload}:{signature}"


def test_sign_and_verify_state_round_trips():
    state = calendar_oauth._sign_state("some-business-id")

    assert calendar_oauth._verify_state(state) == "some-business-id"


def test_verify_state_rejects_tampered_signature():
    state = calendar_oauth._sign_state("some-business-id")
    business_id, timestamp, _signature = state.split(":")
    tampered = f"{business_id}:{timestamp}:0" * 1

    try:
        calendar_oauth._verify_state(tampered)
        assert False, "expected ValueError"
    except ValueError:
        pass


def test_verify_state_rejects_expired_state():
    try:
        calendar_oauth._verify_state(_expired_state("some-business-id"))
        assert False, "expected ValueError"
    except ValueError:
        pass


def test_authorize_requires_login(client):
    resp = client.get("/api/businesses/me/calendar/authorize", follow_redirects=False)

    assert resp.status_code == 401


def test_authorize_requires_booking_enabled_plan(client, business):
    # Free plan (business fixture's default) doesn't include booking_enabled.
    resp = client.get(
        "/api/businesses/me/calendar/authorize", headers=business["headers"], follow_redirects=False
    )

    assert resp.status_code == 403


def test_authorize_503_when_oauth_client_not_configured(client, business, set_plan, monkeypatch):
    set_plan(business["business_id"], "business")
    monkeypatch.setattr(settings, "google_calendar_oauth_client_id", "")
    monkeypatch.setattr(settings, "google_calendar_oauth_client_secret", "")

    resp = client.get(
        "/api/businesses/me/calendar/authorize", headers=business["headers"], follow_redirects=False
    )

    assert resp.status_code == 503


def test_authorize_redirects_to_google_consent_screen(client, business, set_plan, monkeypatch):
    set_plan(business["business_id"], "business")
    monkeypatch.setattr(settings, "google_calendar_oauth_client_id", "test-client-id")
    monkeypatch.setattr(settings, "google_calendar_oauth_client_secret", "test-client-secret")
    fake_flow = MagicMock()
    fake_flow.authorization_url.return_value = ("https://accounts.google.com/o/oauth2/auth?fake=1", "unused")
    monkeypatch.setattr(calendar_oauth, "_build_flow", lambda: fake_flow)

    resp = client.get(
        "/api/businesses/me/calendar/authorize", headers=business["headers"], follow_redirects=False
    )

    assert resp.status_code in (302, 307)
    assert resp.headers["location"] == "https://accounts.google.com/o/oauth2/auth?fake=1"
    _, call_kwargs = fake_flow.authorization_url.call_args
    # access_type=offline + prompt=consent -- without both, a reconnecting
    # business (or one connecting to this OAuth client for a second time)
    # would silently get no refresh_token back at all (see authorize()'s
    # own comment on this).
    assert call_kwargs["access_type"] == "offline"
    assert call_kwargs["prompt"] == "consent"
    assert calendar_oauth._verify_state(call_kwargs["state"]) == business["business_id"]


def test_callback_missing_code_redirects_to_error(client):
    resp = client.get("/api/businesses/me/calendar/callback", follow_redirects=False)

    assert resp.status_code in (302, 307)
    assert "calendar=error" in resp.headers["location"]


def test_callback_invalid_state_redirects_to_error(client):
    resp = client.get(
        "/api/businesses/me/calendar/callback",
        params={"code": "abc", "state": "not-a-valid-state"},
        follow_redirects=False,
    )

    assert resp.status_code in (302, 307)
    assert "calendar=error" in resp.headers["location"]


def test_callback_expired_state_redirects_to_error(client, business):
    resp = client.get(
        "/api/businesses/me/calendar/callback",
        params={"code": "abc", "state": _expired_state(business["business_id"])},
        follow_redirects=False,
    )

    assert resp.status_code in (302, 307)
    assert "calendar=error" in resp.headers["location"]


def test_callback_no_refresh_token_redirects_to_error(client, business, monkeypatch):
    """Google only issues a refresh_token on the FIRST consent for a given
    account+app -- without access_type=offline + prompt=consent (see
    authorize()) a reconnect could come back with none at all. Must not
    silently "connect" with nothing usable."""
    state = calendar_oauth._sign_state(business["business_id"])
    fake_credentials = MagicMock(refresh_token=None)
    fake_flow = MagicMock()
    fake_flow.credentials = fake_credentials
    monkeypatch.setattr(calendar_oauth, "_build_flow", lambda: fake_flow)

    resp = client.get(
        "/api/businesses/me/calendar/callback",
        params={"code": "auth-code", "state": state},
        follow_redirects=False,
    )

    assert "calendar=error" in resp.headers["location"]


def test_callback_success_creates_connection(client, business, db_session, monkeypatch):
    state = calendar_oauth._sign_state(business["business_id"])
    fake_credentials = MagicMock(refresh_token="real-refresh-token")
    fake_flow = MagicMock()
    fake_flow.credentials = fake_credentials
    monkeypatch.setattr(calendar_oauth, "_build_flow", lambda: fake_flow)
    monkeypatch.setattr(calendar_oauth, "_fetch_google_account_email", lambda credentials: "owner@example.com")

    resp = client.get(
        "/api/businesses/me/calendar/callback",
        params={"code": "auth-code", "state": state},
        follow_redirects=False,
    )

    assert resp.status_code in (302, 307)
    assert "calendar=connected" in resp.headers["location"]
    fake_flow.fetch_token.assert_called_once()

    connection = (
        db_session.query(CalendarConnection)
        .filter(CalendarConnection.business_id == business["business_id"])
        .first()
    )
    assert connection is not None
    assert connection.google_account_email == "owner@example.com"
    assert connection.calendar_id == "primary"
    assert decrypt(connection.refresh_token_encrypted) == "real-refresh-token"


def test_callback_reconnect_overwrites_existing_connection(client, business, db_session, monkeypatch):
    db_session.add(
        CalendarConnection(
            business_id=business["business_id"],
            refresh_token_encrypted="irrelevant-old-value",
            google_account_email="old@example.com",
        )
    )
    db_session.commit()

    state = calendar_oauth._sign_state(business["business_id"])
    fake_credentials = MagicMock(refresh_token="new-refresh-token")
    fake_flow = MagicMock()
    fake_flow.credentials = fake_credentials
    monkeypatch.setattr(calendar_oauth, "_build_flow", lambda: fake_flow)
    monkeypatch.setattr(calendar_oauth, "_fetch_google_account_email", lambda credentials: "new@example.com")

    client.get(
        "/api/businesses/me/calendar/callback",
        params={"code": "auth-code", "state": state},
        follow_redirects=False,
    )

    assert db_session.query(CalendarConnection).filter(
        CalendarConnection.business_id == business["business_id"]
    ).count() == 1
    connection = (
        db_session.query(CalendarConnection)
        .filter(CalendarConnection.business_id == business["business_id"])
        .first()
    )
    assert connection.google_account_email == "new@example.com"
    assert decrypt(connection.refresh_token_encrypted) == "new-refresh-token"


def test_status_when_not_connected(client, business):
    resp = client.get("/api/businesses/me/calendar/status", headers=business["headers"])

    assert resp.status_code == 200
    assert resp.json() == {"connected": False}


def test_status_when_connected(client, business, db_session):
    from app.core.encryption import encrypt

    db_session.add(
        CalendarConnection(
            business_id=business["business_id"],
            refresh_token_encrypted=encrypt("tenant-token"),
            google_account_email="owner@example.com",
            calendar_id="primary",
        )
    )
    db_session.commit()

    resp = client.get("/api/businesses/me/calendar/status", headers=business["headers"])

    body = resp.json()
    assert body["connected"] is True
    assert body["google_account_email"] == "owner@example.com"
    assert body["calendar_id"] == "primary"


def test_disconnect_removes_connection(client, business, db_session):
    from app.core.encryption import encrypt

    db_session.add(
        CalendarConnection(business_id=business["business_id"], refresh_token_encrypted=encrypt("tenant-token"))
    )
    db_session.commit()

    resp = client.delete("/api/businesses/me/calendar", headers=business["headers"])

    assert resp.status_code == 200
    assert resp.json() == {"connected": False}
    assert db_session.query(CalendarConnection).filter(
        CalendarConnection.business_id == business["business_id"]
    ).count() == 0


def test_calendar_endpoints_are_tenant_scoped(client, business, signup, db_session):
    """One business's connection is never visible or touchable via another
    business's session -- the exact cross-tenant leak this whole per-tenant
    design exists to prevent."""
    from app.core.encryption import encrypt

    other = signup()
    db_session.add(
        CalendarConnection(business_id=other["business_id"], refresh_token_encrypted=encrypt("other-token"))
    )
    db_session.commit()

    resp = client.get("/api/businesses/me/calendar/status", headers=business["headers"])
    assert resp.json() == {"connected": False}

    client.delete("/api/businesses/me/calendar", headers=business["headers"])
    assert db_session.query(CalendarConnection).filter(
        CalendarConnection.business_id == other["business_id"]
    ).count() == 1
