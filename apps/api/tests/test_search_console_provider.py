"""Tests for Stage 12's SearchConsoleProvider (app/integrations/
search_console_provider.py). No real call to Google -- requests.post and
the token-refresh helper are mocked at the boundary.
"""
from unittest.mock import MagicMock, patch

import pytest

from app.core.config import settings
from app.core.encryption import encrypt
from app.integrations import search_console_provider as scp
from app.models.seo_google_connection import SeoGoogleConnection


def _fake_response(json_body, status=200):
    resp = MagicMock()
    resp.status_code = status
    resp.json.return_value = json_body
    resp.raise_for_status = MagicMock()
    return resp


@pytest.mark.asyncio
async def test_get_page_search_metrics_matches_by_full_url():
    provider = scp.GoogleSearchConsoleProvider("id", "secret", "refresh-token", "https://greenleaf.test/")
    gsc_response = {
        "rows": [
            {"keys": ["https://greenleaf.test/menu"], "clicks": 12, "impressions": 340, "position": 8.4},
        ]
    }

    with patch.object(scp, "get_access_token", return_value="fake-token"), \
         patch.object(scp.requests, "post", return_value=_fake_response(gsc_response)):
        result = await provider.get_page_search_metrics(
            ["https://greenleaf.test/menu", "https://greenleaf.test/contact"]
        )

    assert result.keys() == {"https://greenleaf.test/menu"}  # /contact has no data -- absent, not zeroed
    metrics = result["https://greenleaf.test/menu"]
    assert metrics.clicks == 12
    assert metrics.impressions == 340
    assert metrics.avg_position == 8.4


@pytest.mark.asyncio
async def test_get_page_search_metrics_returns_empty_on_token_refresh_failure():
    provider = scp.GoogleSearchConsoleProvider("id", "secret", "refresh-token", "https://greenleaf.test/")
    with patch.object(scp, "get_access_token", side_effect=scp.GoogleTokenRefreshError("expired")):
        result = await provider.get_page_search_metrics(["https://greenleaf.test/"])
    assert result == {}


@pytest.mark.asyncio
async def test_get_page_search_metrics_returns_empty_on_request_failure():
    provider = scp.GoogleSearchConsoleProvider("id", "secret", "refresh-token", "https://greenleaf.test/")
    with patch.object(scp, "get_access_token", return_value="fake-token"), \
         patch.object(scp.requests, "post", side_effect=scp.requests.RequestException("boom")):
        result = await provider.get_page_search_metrics(["https://greenleaf.test/"])
    assert result == {}


def test_get_search_console_provider_none_when_client_not_configured(db_session, business, monkeypatch):
    monkeypatch.setattr(settings, "google_analytics_oauth_client_id", "")
    monkeypatch.setattr(settings, "google_analytics_oauth_client_secret", "")
    assert scp.get_search_console_provider(db_session, business["business_id"]) is None


def test_get_search_console_provider_none_when_not_connected(db_session, business, monkeypatch):
    monkeypatch.setattr(settings, "google_analytics_oauth_client_id", "test-id")
    monkeypatch.setattr(settings, "google_analytics_oauth_client_secret", "test-secret")
    assert scp.get_search_console_provider(db_session, business["business_id"]) is None


def test_get_search_console_provider_none_when_connected_but_no_site_set(db_session, business, monkeypatch):
    monkeypatch.setattr(settings, "google_analytics_oauth_client_id", "test-id")
    monkeypatch.setattr(settings, "google_analytics_oauth_client_secret", "test-secret")
    db_session.add(SeoGoogleConnection(business_id=business["business_id"], refresh_token_encrypted=encrypt("t")))
    db_session.commit()
    assert scp.get_search_console_provider(db_session, business["business_id"]) is None


def test_get_search_console_provider_returns_provider_when_fully_configured(db_session, business, monkeypatch):
    monkeypatch.setattr(settings, "google_analytics_oauth_client_id", "test-id")
    monkeypatch.setattr(settings, "google_analytics_oauth_client_secret", "test-secret")
    db_session.add(SeoGoogleConnection(
        business_id=business["business_id"],
        refresh_token_encrypted=encrypt("real-refresh-token"),
        search_console_site_url="https://greenleaf.test/",
    ))
    db_session.commit()

    provider = scp.get_search_console_provider(db_session, business["business_id"])

    assert isinstance(provider, scp.GoogleSearchConsoleProvider)
    assert provider._refresh_token == "real-refresh-token"
    assert provider._site_url == "https://greenleaf.test/"
