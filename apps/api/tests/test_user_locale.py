"""The dashboard language (users.locale): chosen at sign-up or in the
dashboard, returned by /auth/me, and used for the emails sent to the user or
their business. Emails are captured with a fake provider -- nothing is sent."""

from datetime import datetime, timezone
from types import SimpleNamespace

import pytest

from app import notifications
from app.core.locale import business_locale, normalize_locale


class _Outbox:
    def __init__(self):
        self.sent = []

    async def send_email(self, to, subject, html, headers=None):
        self.sent.append({"to": to, "subject": subject, "html": html})


@pytest.fixture()
def outbox(monkeypatch):
    box = _Outbox()
    monkeypatch.setattr(notifications, "get_notification_provider", lambda: box)
    return box


def test_normalize_locale():
    assert normalize_locale("no") == "nb"
    assert normalize_locale("nb-NO") == "nb"
    assert normalize_locale("nn") == "nb"
    assert normalize_locale("en_GB") == "en"
    assert normalize_locale("de") is None
    assert normalize_locale(None) is None


def test_signup_saves_the_sign_up_page_language(client, signup):
    biz = signup(locale="no")
    me = client.get("/api/auth/me", headers=biz["headers"])
    assert me.json()["locale"] == "nb"


def test_signup_without_a_language_leaves_it_unset(client, signup):
    biz = signup()
    assert client.get("/api/auth/me", headers=biz["headers"]).json()["locale"] is None


def test_an_unknown_language_at_signup_is_ignored(client, signup):
    biz = signup(locale="klingon")
    assert client.get("/api/auth/me", headers=biz["headers"]).json()["locale"] is None


def test_preference_is_saved_and_restored_at_next_login(client, signup):
    biz = signup()
    resp = client.patch("/api/auth/me/preferences", json={"locale": "nb"}, headers=biz["headers"])
    assert resp.status_code == 200
    assert resp.json()["locale"] == "nb"

    client.cookies.clear()
    login = client.post("/api/auth/login", json={"email": biz["email"], "password": biz["password"]})
    assert login.json()["locale"] == "nb"


def test_preference_rejects_unsupported_languages(client, signup):
    biz = signup()
    resp = client.patch("/api/auth/me/preferences", json={"locale": "nn"}, headers=biz["headers"])
    assert resp.status_code == 422


def test_preference_requires_sign_in(client):
    assert client.patch("/api/auth/me/preferences", json={"locale": "nb"}).status_code == 401


def test_business_locale_follows_the_owner(db_session, signup):
    biz = signup(locale="nb")
    assert business_locale(db_session, biz["business_id"]) == "nb"
    other = signup()
    assert business_locale(db_session, other["business_id"]) == "en"


def test_password_reset_email_uses_the_users_language(client, db_session, signup, outbox):
    biz = signup(locale="nb")
    client.cookies.clear()
    client.post("/api/auth/forgot-password", json={"email": biz["email"]})

    assert len(outbox.sent) == 1
    assert outbox.sent[0]["subject"] == "Tilbakestill passordet ditt for Mielikkix"
    assert "Tilbakestill passordet" in outbox.sent[0]["html"]


@pytest.mark.asyncio
async def test_new_lead_email_translates_labels_not_the_lead(outbox):
    lead = SimpleNamespace(name="Kari Nordmann", email="kari@example.no", phone=None, message="Can you call me?")
    await notifications.notify_new_lead("Frisør AS", "owner@example.no", lead, "nb")

    mail = outbox.sent[0]
    assert mail["subject"] == "Ny lead fra Frisør AS"
    assert "<strong>Navn:</strong> Kari Nordmann" in mail["html"]
    assert "Can you call me?" in mail["html"]  # the visitor's own words are never translated


@pytest.mark.asyncio
async def test_quota_warning_in_norwegian_uses_norwegian_numbers(outbox):
    await notifications.notify_quota_warning(["o@example.no"], "Frisør AS", "Business", 80, 1600, 2000, "nb")
    mail = outbox.sent[0]
    assert mail["subject"] == "Frisør AS har brukt 80 % av AI-samtalene denne måneden"
    assert "1 600" in mail["html"] and "2 000" in mail["html"]


@pytest.mark.asyncio
async def test_english_stays_the_default(outbox):
    await notifications.notify_quota_warning(["o@example.com"], "Shop", "Business", 80, 1600, 2000)
    assert outbox.sent[0]["subject"] == "Shop has used 80% of its AI conversations this month"


@pytest.mark.asyncio
async def test_deletion_scheduled_email_in_norwegian_has_a_norwegian_date(outbox):
    when = datetime(2026, 11, 4, tzinfo=timezone.utc)
    await notifications.notify_account_deletion_scheduled("o@example.no", "Kari", "Frisør AS", when, "nb")
    assert "4. november 2026" in outbox.sent[0]["html"]


@pytest.mark.asyncio
async def test_account_deleted_email_is_bilingual(outbox):
    await notifications.notify_account_deleted("o@example.no", "Frisør AS")
    html = outbox.sent[0]["html"]
    assert "er nå slettet permanent" in html and "permanently deleted" in html


def test_new_lead_notification_uses_the_owners_language(client, signup, outbox):
    biz = signup(locale="nb")
    client.cookies.clear()
    resp = client.post(
        "/api/leads",
        json={"business_id": biz["business_id"], "name": "Ola", "email": "ola@example.no", "message": "Hei"},
    )
    assert resp.status_code == 201, resp.text
    assert outbox.sent and outbox.sent[-1]["subject"].startswith("Ny lead fra")
