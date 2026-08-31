"""get_calendar_provider() -- the seam between Mielikkix's own demo
calendar and a real business's own connected one (see
calendar_provider.py's own docstring). Uses the isolated `client`/
`db_session` fixtures since it queries the CalendarConnection table.
"""

from app.core.config import settings
from app.core.encryption import encrypt
from app.integrations.calendar_provider import get_calendar_provider
from app.integrations.google_calendar_client import GoogleCalendarProvider
from app.models.calendar_connection import CalendarConnection


def test_no_business_id_returns_the_global_demo_provider(db_session):
    provider = get_calendar_provider(db_session, None)

    assert isinstance(provider, GoogleCalendarProvider)
    assert provider.client_id == settings.google_calendar_client_id
    assert provider.refresh_token == settings.google_calendar_refresh_token


def test_no_db_returns_the_global_demo_provider():
    provider = get_calendar_provider(None, "some-business-id")

    assert isinstance(provider, GoogleCalendarProvider)
    assert provider.refresh_token == settings.google_calendar_refresh_token


def test_business_with_no_connection_returns_none(db_session, business):
    provider = get_calendar_provider(db_session, business["business_id"])

    assert provider is None


def test_business_with_a_connection_gets_its_own_credentials(db_session, business, monkeypatch):
    monkeypatch.setattr(settings, "google_calendar_oauth_client_id", "web-app-client-id")
    monkeypatch.setattr(settings, "google_calendar_oauth_client_secret", "web-app-secret")
    db_session.add(
        CalendarConnection(
            business_id=business["business_id"],
            refresh_token_encrypted=encrypt("tenant-refresh-token"),
            calendar_id="tenant@example.com",
        )
    )
    db_session.commit()

    provider = get_calendar_provider(db_session, business["business_id"])

    assert isinstance(provider, GoogleCalendarProvider)
    assert provider.client_id == "web-app-client-id"
    assert provider.client_secret == "web-app-secret"
    # Decrypted, never the raw encrypted column value -- this is the whole
    # point of storing it encrypted (see core/encryption.py).
    assert provider.refresh_token == "tenant-refresh-token"
    assert provider.calendar_id == "tenant@example.com"


def test_two_businesses_get_independently_isolated_providers(db_session, business, signup):
    other = signup()
    monkeypatch_targets = [business, other]
    tokens = ["biz-a-token", "biz-b-token"]
    for biz, token in zip(monkeypatch_targets, tokens):
        db_session.add(
            CalendarConnection(
                business_id=biz["business_id"],
                refresh_token_encrypted=encrypt(token),
                calendar_id=f"{biz['business_id']}@example.com",
            )
        )
    db_session.commit()

    provider_a = get_calendar_provider(db_session, business["business_id"])
    provider_b = get_calendar_provider(db_session, other["business_id"])

    assert provider_a.refresh_token == "biz-a-token"
    assert provider_b.refresh_token == "biz-b-token"
    assert provider_a.calendar_id != provider_b.calendar_id
