"""GDPR Phase 3: sign-up consent (see GDPR-COMPLIANCE-CLAUDE.md)."""
import asyncio
from urllib.parse import parse_qs, urlparse

import pytest

from app import notifications
from app.core.legal import DPA_VERSION, TERMS_VERSION
from app.models.consent_record import ConsentRecord
from app.models.user import User
from app.services import consent_service

BASE = {
    "business_name": "Consent Shop",
    "business_slug": "consent-shop",
    "industry": "retail",
    "full_name": "Owner",
    "email": "owner@consentshop.com",
    "password": "secret12345",
}
VALID = {**BASE, "country": "NO", "terms_accepted": True, "age_confirmed": True}


def _no_user_created(db_session):
    return db_session.query(User).filter(User.email == BASE["email"]).count() == 0


@pytest.mark.parametrize(
    "payload",
    [
        pytest.param({k: v for k, v in VALID.items() if k != "terms_accepted"}, id="terms-missing"),
        pytest.param({**VALID, "terms_accepted": False}, id="terms-false"),
        pytest.param({k: v for k, v in VALID.items() if k != "age_confirmed"}, id="age-missing"),
        pytest.param({**VALID, "age_confirmed": False}, id="age-false"),
        pytest.param({k: v for k, v in VALID.items() if k != "country"}, id="country-missing"),
        pytest.param({**VALID, "country": "ZZ"}, id="country-unknown"),
        pytest.param({**VALID, "terms_accepted": None}, id="terms-null"),
        pytest.param(BASE, id="old-client-no-consent-fields"),
    ],
)
def test_register_rejected_without_required_consent(client, db_session, payload):
    resp = client.post("/api/auth/register", json=payload)
    assert resp.status_code == 422, resp.text
    assert _no_user_created(db_session)
    assert db_session.query(ConsentRecord).count() == 0
    assert not resp.cookies.get("access_token")


def test_register_records_consents_with_versions(client, db_session):
    resp = client.post("/api/auth/register", json=VALID)
    assert resp.status_code == 200, resp.text

    user = db_session.query(User).filter(User.email == BASE["email"]).one()
    assert user.country == "NO"
    rows = {r.type: r for r in db_session.query(ConsentRecord).filter(ConsentRecord.user_id == user.id)}
    assert set(rows) == {"terms", "dpa", "age_confirmation", "marketing_email"}
    assert rows["terms"].granted and rows["terms"].document_version == TERMS_VERSION
    assert rows["dpa"].granted and rows["dpa"].document_version == DPA_VERSION
    assert rows["age_confirmation"].granted
    # Not ticked -> still recorded, as declined (never defaulted to granted).
    assert rows["marketing_email"].granted is False
    assert all(r.source == "register" for r in rows.values())
    # Keyed hash only, never the raw client IP.
    assert all(r.ip_hash and r.ip_hash != "testclient" and len(r.ip_hash) == 64 for r in rows.values())
    assert not consent_service.has_marketing_consent(db_session, user.id)


def test_register_country_is_normalised(client, db_session):
    resp = client.post("/api/auth/register", json={**VALID, "country": " gb "})
    assert resp.status_code == 200, resp.text
    assert db_session.query(User).filter(User.email == BASE["email"]).one().country == "GB"


def test_marketing_opt_in_recorded(client, db_session):
    resp = client.post("/api/auth/register", json={**VALID, "marketing_opt_in": True})
    assert resp.status_code == 200, resp.text
    user = db_session.query(User).filter(User.email == BASE["email"]).one()
    assert consent_service.has_marketing_consent(db_session, user.id)


class _FakeProvider:
    def __init__(self):
        self.sent = []

    async def send_email(self, to, subject, html, headers=None):
        self.sent.append({"to": to, "subject": subject, "html": html, "headers": headers})


@pytest.fixture()
def fake_provider(monkeypatch):
    provider = _FakeProvider()
    monkeypatch.setattr(notifications, "get_notification_provider", lambda: provider)
    return provider


def _register(client, db_session, marketing):
    resp = client.post("/api/auth/register", json={**VALID, "marketing_opt_in": marketing})
    assert resp.status_code == 200, resp.text
    client.cookies.clear()
    return db_session.query(User).filter(User.email == BASE["email"]).one()


def test_no_marketing_email_without_consent(client, db_session, fake_provider):
    user = _register(client, db_session, marketing=False)
    sent = asyncio.run(notifications.send_marketing_email(db_session, user, "News", "<p>Hi</p>"))
    assert sent is False
    assert fake_provider.sent == []


def test_transactional_email_unaffected_by_marketing_choice(client, db_session, fake_provider):
    _register(client, db_session, marketing=False)
    resp = client.post("/api/auth/forgot-password", json={"email": BASE["email"]})
    assert resp.status_code == 200
    assert len(fake_provider.sent) == 1 and "Reset your Mielikkix password" in fake_provider.sent[0]["subject"]


def test_marketing_email_has_working_one_click_unsubscribe(client, db_session, fake_provider):
    user = _register(client, db_session, marketing=True)
    assert asyncio.run(notifications.send_marketing_email(db_session, user, "News", "<p>Hi</p>")) is True

    email = fake_provider.sent[0]
    assert email["headers"]["List-Unsubscribe-Post"] == "List-Unsubscribe=One-Click"
    url = email["headers"]["List-Unsubscribe"].strip("<>")
    assert url in email["html"]
    token = parse_qs(urlparse(url).query)["token"][0]

    # RFC 8058 one-click: the mail client POSTs, no login needed.
    resp = client.post(f"/api/consent/unsubscribe?token={token}")
    assert resp.status_code == 200 and "unsubscribed" in resp.text
    assert not consent_service.has_marketing_consent(db_session, user.id)

    history = (
        db_session.query(ConsentRecord)
        .filter(ConsentRecord.user_id == user.id, ConsentRecord.type == "marketing_email")
        .order_by(ConsentRecord.granted_at)
        .all()
    )
    assert [(r.granted, r.source) for r in history] == [(True, "register"), (False, "unsubscribe")]
    assert history[0].withdrawn_at is not None

    # Repeat clicks (GET link in the body) are idempotent: no extra rows.
    assert client.get(f"/api/consent/unsubscribe?token={token}").status_code == 200
    assert db_session.query(ConsentRecord).filter(ConsentRecord.type == "marketing_email").count() == 2

    fake_provider.sent.clear()
    assert asyncio.run(notifications.send_marketing_email(db_session, user, "News", "<p>Hi</p>")) is False
    assert fake_provider.sent == []


def test_unsubscribe_rejects_bad_tokens(client, db_session):
    user = _register(client, db_session, marketing=True)
    session_token = client.post("/api/auth/login", json={"email": BASE["email"], "password": BASE["password"]}).cookies.get("access_token")
    for token in ["garbage", session_token]:
        assert client.get(f"/api/consent/unsubscribe?token={token}").status_code == 400
    assert consent_service.has_marketing_consent(db_session, user.id)


def test_unsubscribe_token_is_not_a_session_token(client, db_session):
    user = _register(client, db_session, marketing=True)
    token = consent_service.make_unsubscribe_token(user.id)
    resp = client.get("/api/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 401
