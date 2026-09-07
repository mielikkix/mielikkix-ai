"""Review & Reputation Agent: real per-tenant Google Business Profile OAuth
(app/api/review_oauth.py). No test here makes a real call to Google --
google_auth_oauthlib.flow.Flow is mocked at the boundary (via
review_oauth._build_flow), same convention test_calendar_oauth.py already
uses for the analogous Calendar flow, and GoogleReviewsClient's
get_accounts/get_locations/get_review are mocked the same way
test_google_reviews_client.py mocks the underlying requests/Credentials.refresh
boundary -- here we mock one level higher (the client class itself) since
these tests are about review_oauth.py's own callback logic, not about the
Google API wire format (already covered by test_google_reviews_client.py).
"""

import hashlib
import hmac
import time
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.api import review_oauth
from app.core.config import settings
from app.core.encryption import decrypt
from app.models.review_connection import ReviewConnection


def _expired_state(business_id: str) -> str:
    old_timestamp = int(time.time()) - review_oauth._STATE_TTL_SECONDS - 10
    payload = f"{business_id}:{old_timestamp}"
    signature = hmac.new(settings.secret_key.encode(), payload.encode(), hashlib.sha256).hexdigest()
    return f"{payload}:{signature}"


def _fake_credentials(refresh_token="fake-refresh-token"):
    creds = MagicMock()
    creds.refresh_token = refresh_token
    return creds


def _patch_flow(monkeypatch, credentials):
    fake_flow = MagicMock()
    fake_flow.credentials = credentials
    monkeypatch.setattr(review_oauth, "_build_flow", lambda: fake_flow)
    return fake_flow


def _patch_client(monkeypatch, accounts=None, locations=None):
    """Patches review_oauth.GoogleReviewsClient itself (the class
    review_oauth.py's callback constructs directly) with a fake whose
    get_accounts/get_locations are AsyncMocks -- these two methods'
    own real HTTP/parsing behavior is test_google_reviews_client.py's
    job, not this file's."""
    fake_client = MagicMock()
    fake_client.get_accounts = AsyncMock(return_value=accounts if accounts is not None else [])
    fake_client.get_locations = AsyncMock(return_value=locations if locations is not None else [])
    monkeypatch.setattr(review_oauth, "GoogleReviewsClient", MagicMock(return_value=fake_client))
    return fake_client


def test_sign_and_verify_state_round_trips():
    state = review_oauth._sign_state("some-business-id")

    assert review_oauth._verify_state(state) == "some-business-id"


def test_verify_state_rejects_tampered_signature():
    state = review_oauth._sign_state("some-business-id")
    business_id, timestamp, _signature = state.split(":")
    tampered = f"{business_id}:{timestamp}:0"

    with pytest.raises(ValueError):
        review_oauth._verify_state(tampered)


def test_verify_state_rejects_expired_state():
    with pytest.raises(ValueError):
        review_oauth._verify_state(_expired_state("some-business-id"))


def test_authorize_requires_login(client):
    resp = client.get("/api/businesses/me/reviews/authorize", follow_redirects=False)

    assert resp.status_code == 401


def test_authorize_requires_review_reputation_enabled_plan(client, business):
    # Free plan (business fixture's default) doesn't include review_reputation_enabled.
    resp = client.get("/api/businesses/me/reviews/authorize", headers=business["headers"], follow_redirects=False)

    assert resp.status_code == 403


def test_authorize_503_when_oauth_client_not_configured(client, business, set_plan, monkeypatch):
    set_plan(business["business_id"], "business")
    monkeypatch.setattr(settings, "google_reviews_oauth_client_id", "")
    monkeypatch.setattr(settings, "google_reviews_oauth_client_secret", "")

    resp = client.get("/api/businesses/me/reviews/authorize", headers=business["headers"], follow_redirects=False)

    assert resp.status_code == 503


def test_authorize_redirects_to_google_consent_screen(client, business, set_plan, monkeypatch):
    set_plan(business["business_id"], "business")
    monkeypatch.setattr(settings, "google_reviews_oauth_client_id", "test-client-id")
    monkeypatch.setattr(settings, "google_reviews_oauth_client_secret", "test-client-secret")
    fake_flow = MagicMock()
    fake_flow.authorization_url.return_value = ("https://accounts.google.com/o/oauth2/auth?fake=1", "unused")
    monkeypatch.setattr(review_oauth, "_build_flow", lambda: fake_flow)

    resp = client.get("/api/businesses/me/reviews/authorize", headers=business["headers"], follow_redirects=False)

    assert resp.status_code in (302, 307)
    assert resp.headers["location"] == "https://accounts.google.com/o/oauth2/auth?fake=1"
    _, call_kwargs = fake_flow.authorization_url.call_args
    assert call_kwargs["access_type"] == "offline"
    assert call_kwargs["prompt"] == "consent"
    assert review_oauth._verify_state(call_kwargs["state"]) == business["business_id"]


def test_callback_missing_code_redirects_to_error(client):
    resp = client.get("/api/businesses/me/reviews/callback", follow_redirects=False)

    assert resp.status_code in (302, 307)
    assert "google_reviews=error" in resp.headers["location"]


def test_callback_invalid_state_redirects_to_error(client):
    resp = client.get(
        "/api/businesses/me/reviews/callback", params={"code": "abc", "state": "garbage"}, follow_redirects=False
    )

    assert "google_reviews=error" in resp.headers["location"]


def test_callback_expired_state_redirects_to_error(client, business):
    resp = client.get(
        "/api/businesses/me/reviews/callback",
        params={"code": "abc", "state": _expired_state(business["business_id"])},
        follow_redirects=False,
    )

    assert "google_reviews=error" in resp.headers["location"]


def test_callback_no_refresh_token_redirects_to_error(client, business, monkeypatch):
    state = review_oauth._sign_state(business["business_id"])
    _patch_flow(monkeypatch, _fake_credentials(refresh_token=None))

    resp = client.get(
        "/api/businesses/me/reviews/callback", params={"code": "abc", "state": state}, follow_redirects=False
    )

    assert "google_reviews=error" in resp.headers["location"]


def test_callback_zero_accounts_redirects_to_error(client, business, monkeypatch):
    state = review_oauth._sign_state(business["business_id"])
    _patch_flow(monkeypatch, _fake_credentials())
    _patch_client(monkeypatch, accounts=[])

    resp = client.get(
        "/api/businesses/me/reviews/callback", params={"code": "abc", "state": state}, follow_redirects=False
    )

    assert "google_reviews=error" in resp.headers["location"]


def test_callback_success_with_single_location_auto_selects_it(client, business, db_session, monkeypatch):
    state = review_oauth._sign_state(business["business_id"])
    _patch_flow(monkeypatch, _fake_credentials(refresh_token="real-refresh-token"))
    _patch_client(
        monkeypatch,
        accounts=[{"name": "accounts/123", "accountName": "My Business"}],
        locations=[{"name": "accounts/123/locations/456", "title": "Downtown Branch"}],
    )
    monkeypatch.setattr(review_oauth, "_fetch_google_account_email", lambda credentials: "owner@example.com")

    resp = client.get(
        "/api/businesses/me/reviews/callback", params={"code": "abc", "state": state}, follow_redirects=False
    )

    assert "google_reviews=connected" in resp.headers["location"]
    connection = db_session.query(ReviewConnection).filter(ReviewConnection.business_id == business["business_id"]).first()
    assert connection is not None
    assert connection.account_id == "123"
    assert connection.location_id == "456"
    assert connection.location_title == "Downtown Branch"
    assert connection.google_account_email == "owner@example.com"
    assert decrypt(connection.refresh_token_encrypted) == "real-refresh-token"


def test_callback_with_multiple_locations_leaves_location_null(client, business, db_session, monkeypatch):
    state = review_oauth._sign_state(business["business_id"])
    _patch_flow(monkeypatch, _fake_credentials())
    _patch_client(
        monkeypatch,
        accounts=[{"name": "accounts/123", "accountName": "My Business"}],
        locations=[
            {"name": "accounts/123/locations/456", "title": "Downtown Branch"},
            {"name": "accounts/123/locations/789", "title": "Uptown Branch"},
        ],
    )

    resp = client.get(
        "/api/businesses/me/reviews/callback", params={"code": "abc", "state": state}, follow_redirects=False
    )

    assert "google_reviews=choose_location" in resp.headers["location"]
    connection = db_session.query(ReviewConnection).filter(ReviewConnection.business_id == business["business_id"]).first()
    assert connection is not None
    assert connection.account_id == "123"
    assert connection.location_id is None


def test_status_when_not_connected(client, business):
    resp = client.get("/api/businesses/me/reviews/status", headers=business["headers"])

    assert resp.status_code == 200
    assert resp.json() == {"connected": False, "needs_location": False, "configured": False}


def test_status_reports_configured_when_oauth_client_is_set(client, business, monkeypatch):
    monkeypatch.setattr(settings, "google_reviews_oauth_client_id", "test-client-id")
    monkeypatch.setattr(settings, "google_reviews_oauth_client_secret", "test-client-secret")

    resp = client.get("/api/businesses/me/reviews/status", headers=business["headers"])

    assert resp.json()["configured"] is True


def test_status_needs_location_when_not_yet_chosen(client, business, db_session):
    connection = ReviewConnection(
        business_id=business["business_id"],
        refresh_token_encrypted="irrelevant",
        account_id="123",
        location_id=None,
    )
    db_session.add(connection)
    db_session.commit()

    resp = client.get("/api/businesses/me/reviews/status", headers=business["headers"])

    body = resp.json()
    assert body["connected"] is False
    assert body["needs_location"] is True


def test_status_when_fully_connected(client, business, db_session):
    connection = ReviewConnection(
        business_id=business["business_id"],
        refresh_token_encrypted="irrelevant",
        account_id="123",
        location_id="456",
        location_title="Downtown Branch",
        google_account_email="owner@example.com",
    )
    db_session.add(connection)
    db_session.commit()

    resp = client.get("/api/businesses/me/reviews/status", headers=business["headers"])

    body = resp.json()
    assert body["connected"] is True
    assert body["needs_location"] is False
    assert body["location_title"] == "Downtown Branch"


def test_list_locations_requires_existing_connection(client, business):
    resp = client.get("/api/businesses/me/reviews/locations", headers=business["headers"])

    assert resp.status_code == 404


def test_list_locations_returns_options_for_the_connected_account(client, business, db_session, monkeypatch):
    from app.core.encryption import encrypt

    connection = ReviewConnection(
        business_id=business["business_id"],
        refresh_token_encrypted=encrypt("real-refresh-token"),
        account_id="123",
        location_id=None,
    )
    db_session.add(connection)
    db_session.commit()
    _patch_client(monkeypatch, locations=[{"name": "accounts/123/locations/456", "title": "Downtown Branch"}])

    resp = client.get("/api/businesses/me/reviews/locations", headers=business["headers"])

    assert resp.status_code == 200
    assert resp.json() == [{"location_id": "456", "title": "Downtown Branch"}]


def test_select_location_finalizes_connection(client, business, db_session):
    connection = ReviewConnection(
        business_id=business["business_id"],
        refresh_token_encrypted="irrelevant",
        account_id="123",
        location_id=None,
    )
    db_session.add(connection)
    db_session.commit()

    resp = client.post(
        "/api/businesses/me/reviews/select-location",
        json={"location_id": "456", "title": "Downtown Branch"},
        headers=business["headers"],
    )

    assert resp.status_code == 200
    db_session.refresh(connection)
    assert connection.location_id == "456"
    assert connection.location_title == "Downtown Branch"


def test_select_location_requires_existing_connection(client, business):
    resp = client.post(
        "/api/businesses/me/reviews/select-location", json={"location_id": "456"}, headers=business["headers"]
    )

    assert resp.status_code == 404


def test_disconnect_removes_connection(client, business, db_session):
    connection = ReviewConnection(
        business_id=business["business_id"], refresh_token_encrypted="irrelevant", account_id="123", location_id="456"
    )
    db_session.add(connection)
    db_session.commit()

    resp = client.delete("/api/businesses/me/reviews", headers=business["headers"])

    assert resp.status_code == 200
    assert db_session.query(ReviewConnection).filter(ReviewConnection.business_id == business["business_id"]).first() is None


def test_review_oauth_status_is_tenant_scoped(client, business, signup, db_session):
    other = signup()
    connection = ReviewConnection(
        business_id=other["business_id"], refresh_token_encrypted="irrelevant", account_id="123", location_id="456"
    )
    db_session.add(connection)
    db_session.commit()

    resp = client.get("/api/businesses/me/reviews/status", headers=business["headers"])

    assert resp.json() == {"connected": False, "needs_location": False, "configured": False}
