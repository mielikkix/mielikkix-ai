"""Tests for Stage 8 (apps/agents/seo-copywriter/CLAUDE.md): the
PerformanceProvider abstraction and its Google PageSpeed Insights
implementation. No real network calls -- httpx is always mocked.
"""
import httpx
import pytest

from app.core.config import settings
from app.integrations import performance_provider as pp


def _fake_response(payload: dict, status: int = 200) -> httpx.Response:
    return httpx.Response(status, json=payload, request=httpx.Request("GET", "https://example.com"))


class _FakeAsyncClient:
    def __init__(self, response):
        self._response = response

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False

    async def get(self, url, **kwargs):
        return self._response


def _patch_client(monkeypatch, response):
    monkeypatch.setattr(pp.httpx, "AsyncClient", lambda *a, **k: _FakeAsyncClient(response))


LIGHTHOUSE_PAYLOAD = {
    "lighthouseResult": {
        "categories": {"performance": {"score": 0.87}},
        "audits": {
            "largest-contentful-paint": {"numericValue": 2400.7},
            "cumulative-layout-shift": {"numericValue": 0.045},
            "total-blocking-time": {"numericValue": 150.2},
        },
    },
}

LIGHTHOUSE_PAYLOAD_WITH_FIELD_DATA = {
    **LIGHTHOUSE_PAYLOAD,
    "loadingExperience": {"metrics": {"INTERACTION_TO_NEXT_PAINT": {"percentile": 180}}},
}


@pytest.mark.asyncio
async def test_no_api_key_returns_none_without_any_network_call(monkeypatch):
    monkeypatch.setattr(settings, "google_pagespeed_api_key", "")
    called = False

    def fail_if_called(*a, **k):
        nonlocal called
        called = True
        raise AssertionError("should never construct a client with no API key")

    monkeypatch.setattr(pp.httpx, "AsyncClient", fail_if_called)

    provider = pp.GooglePageSpeedProvider()
    result = await provider.measure("https://greenleaf.test", "mobile")

    assert result is None
    assert called is False


@pytest.mark.asyncio
async def test_successful_measurement_parses_core_fields(monkeypatch):
    monkeypatch.setattr(settings, "google_pagespeed_api_key", "fake-key")
    _patch_client(monkeypatch, _fake_response(LIGHTHOUSE_PAYLOAD))

    provider = pp.GooglePageSpeedProvider()
    result = await provider.measure("https://greenleaf.test", "mobile")

    assert result is not None
    assert result.strategy == "mobile"
    assert result.performance_score == 87
    assert result.lcp_ms == 2401
    assert result.cls == 0.045
    assert result.tbt_ms == 150


@pytest.mark.asyncio
async def test_inp_is_none_without_real_field_data(monkeypatch):
    """No loadingExperience in the response (typical for a lower-traffic
    site) -- inp_ms must stay None, never backfilled from tbt_ms."""
    monkeypatch.setattr(settings, "google_pagespeed_api_key", "fake-key")
    _patch_client(monkeypatch, _fake_response(LIGHTHOUSE_PAYLOAD))

    provider = pp.GooglePageSpeedProvider()
    result = await provider.measure("https://greenleaf.test", "mobile")

    assert result.inp_ms is None
    assert result.tbt_ms == 150


@pytest.mark.asyncio
async def test_inp_uses_real_field_data_when_present(monkeypatch):
    monkeypatch.setattr(settings, "google_pagespeed_api_key", "fake-key")
    _patch_client(monkeypatch, _fake_response(LIGHTHOUSE_PAYLOAD_WITH_FIELD_DATA))

    provider = pp.GooglePageSpeedProvider()
    result = await provider.measure("https://greenleaf.test", "mobile")

    assert result.inp_ms == 180


@pytest.mark.asyncio
async def test_api_error_status_returns_none(monkeypatch):
    monkeypatch.setattr(settings, "google_pagespeed_api_key", "fake-key")
    _patch_client(monkeypatch, _fake_response({}, status=500))

    provider = pp.GooglePageSpeedProvider()
    result = await provider.measure("https://greenleaf.test", "mobile")

    assert result is None


@pytest.mark.asyncio
async def test_network_failure_returns_none_not_raises(monkeypatch):
    monkeypatch.setattr(settings, "google_pagespeed_api_key", "fake-key")

    class _RaisingClient:
        def __init__(self, *a, **k):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *exc):
            return False

        async def get(self, url, **kwargs):
            raise httpx.ConnectError("connection failed")

    monkeypatch.setattr(pp.httpx, "AsyncClient", lambda *a, **k: _RaisingClient())

    provider = pp.GooglePageSpeedProvider()
    result = await provider.measure("https://greenleaf.test", "mobile")

    assert result is None


@pytest.mark.asyncio
async def test_invalid_strategy_raises_value_error(monkeypatch):
    monkeypatch.setattr(settings, "google_pagespeed_api_key", "fake-key")
    provider = pp.GooglePageSpeedProvider()

    with pytest.raises(ValueError):
        await provider.measure("https://greenleaf.test", "tablet")


def test_factory_returns_a_google_provider():
    assert isinstance(pp.get_performance_provider(), pp.GooglePageSpeedProvider)


@pytest.mark.asyncio
async def test_missing_performance_category_returns_none_score(monkeypatch):
    """A malformed/partial Lighthouse response shouldn't crash -- missing
    fields just become None, same 'not measured' rule as no API key."""
    monkeypatch.setattr(settings, "google_pagespeed_api_key", "fake-key")
    _patch_client(monkeypatch, _fake_response({"lighthouseResult": {}}))

    provider = pp.GooglePageSpeedProvider()
    result = await provider.measure("https://greenleaf.test", "mobile")

    assert result is not None
    assert result.performance_score is None
    assert result.lcp_ms is None
