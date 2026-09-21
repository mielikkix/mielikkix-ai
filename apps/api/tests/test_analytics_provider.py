"""Tests for Stage 12's AnalyticsProvider (app/integrations/
analytics_provider.py). No real call to Google -- requests.post and the
token-refresh helper are mocked at the boundary.
"""
from unittest.mock import MagicMock, patch

import pytest

from app.core.config import settings
from app.core.encryption import encrypt
from app.integrations import analytics_provider as ap
from app.models.seo_google_connection import SeoGoogleConnection


def _fake_response(json_body, status=200):
    resp = MagicMock()
    resp.status_code = status
    resp.json.return_value = json_body
    resp.raise_for_status = MagicMock()
    return resp


@pytest.mark.asyncio
async def test_get_page_sessions_matches_by_path():
    provider = ap.GoogleAnalyticsProvider("id", "secret", "refresh-token", "properties/123")
    ga_response = {
        "rows": [
            {"dimensionValues": [{"value": "/menu"}], "metricValues": [{"value": "42"}]},
            {"dimensionValues": [{"value": "/about"}], "metricValues": [{"value": "7"}]},
        ]
    }

    with patch.object(ap, "get_access_token", return_value="fake-token"), \
         patch.object(ap.requests, "post", return_value=_fake_response(ga_response)):
        result = await provider.get_page_sessions(["https://greenleaf.test/menu", "https://greenleaf.test/contact"])

    assert result == {"https://greenleaf.test/menu": 42}  # /contact has no GA data -- absent, not 0


@pytest.mark.asyncio
async def test_get_page_sessions_returns_empty_on_token_refresh_failure():
    provider = ap.GoogleAnalyticsProvider("id", "secret", "refresh-token", "properties/123")
    with patch.object(ap, "get_access_token", side_effect=ap.GoogleTokenRefreshError("expired")):
        result = await provider.get_page_sessions(["https://greenleaf.test/"])
    assert result == {}


@pytest.mark.asyncio
async def test_get_page_sessions_returns_empty_on_request_failure():
    provider = ap.GoogleAnalyticsProvider("id", "secret", "refresh-token", "properties/123")
    with patch.object(ap, "get_access_token", return_value="fake-token"), \
         patch.object(ap.requests, "post", side_effect=ap.requests.RequestException("boom")):
        result = await provider.get_page_sessions(["https://greenleaf.test/"])
    assert result == {}


def test_get_analytics_provider_none_when_client_not_configured(db_session, business, monkeypatch):
    monkeypatch.setattr(settings, "google_analytics_oauth_client_id", "")
    monkeypatch.setattr(settings, "google_analytics_oauth_client_secret", "")
    assert ap.get_analytics_provider(db_session, business["business_id"]) is None


def test_get_analytics_provider_none_when_not_connected(db_session, business, monkeypatch):
    monkeypatch.setattr(settings, "google_analytics_oauth_client_id", "test-id")
    monkeypatch.setattr(settings, "google_analytics_oauth_client_secret", "test-secret")
    assert ap.get_analytics_provider(db_session, business["business_id"]) is None


def test_get_analytics_provider_none_when_connected_but_no_property_set(db_session, business, monkeypatch):
    monkeypatch.setattr(settings, "google_analytics_oauth_client_id", "test-id")
    monkeypatch.setattr(settings, "google_analytics_oauth_client_secret", "test-secret")
    db_session.add(SeoGoogleConnection(business_id=business["business_id"], refresh_token_encrypted=encrypt("t")))
    db_session.commit()
    assert ap.get_analytics_provider(db_session, business["business_id"]) is None


def test_get_analytics_provider_returns_provider_when_fully_configured(db_session, business, monkeypatch):
    monkeypatch.setattr(settings, "google_analytics_oauth_client_id", "test-id")
    monkeypatch.setattr(settings, "google_analytics_oauth_client_secret", "test-secret")
    db_session.add(SeoGoogleConnection(
        business_id=business["business_id"],
        refresh_token_encrypted=encrypt("real-refresh-token"),
        analytics_property_id="properties/123",
    ))
    db_session.commit()

    provider = ap.get_analytics_provider(db_session, business["business_id"])

    assert isinstance(provider, ap.GoogleAnalyticsProvider)
    assert provider._refresh_token == "real-refresh-token"
    assert provider._property_id == "properties/123"
