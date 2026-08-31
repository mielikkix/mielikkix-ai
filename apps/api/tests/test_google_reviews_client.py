"""
Google Reviews client + platform, tested the same way
test_google_calendar_client.py tests google_calendar_client.py: no real
Google account or network call happens here. Two things get mocked at the
boundary:

1. `Credentials.refresh` -- normally makes a real HTTPS call to Google's
   token endpoint to mint an access token from the refresh token. Replaced
   with a no-op so tests never need real OAuth credentials.
2. `requests.get`/`requests.put` -- normally make real HTTP calls to the
   Business Profile REST API (reviews.list / reviews.get / reviews.reply).
   Replaced with fakes that record what was sent and return a canned JSON
   response.
"""

from datetime import datetime, timezone

import pytest
import requests

from app.integrations import google_reviews_client
from app.integrations.google_reviews_client import GoogleReviewsClient, GoogleReviewsError
from app.integrations.review_platforms.google_platform import GoogleReviewsPlatform


class _FakeResponse:
    def __init__(self, json_data: dict, status_code: int = 200):
        self._json_data = json_data
        self.status_code = status_code

    def raise_for_status(self):
        if self.status_code >= 400:
            raise requests.HTTPError(f"{self.status_code} error", response=self)

    def json(self):
        return self._json_data


class _FakeCall:
    """Records every call made through it (not just the last one) -- fetch
    reviews needs multi-call assertions for pagination, unlike the calendar
    client's tests which only ever make one call per test."""

    def __init__(self, responses: list[_FakeResponse]):
        self._responses = list(responses)
        self.calls: list[tuple[str, dict]] = []

    def __call__(self, url, **kwargs):
        self.calls.append((url, kwargs))
        return self._responses.pop(0)

    @property
    def last_url(self):
        return self.calls[-1][0]

    @property
    def last_kwargs(self):
        return self.calls[-1][1]


def _configure_credentials(monkeypatch) -> GoogleReviewsClient:
    monkeypatch.setattr(google_reviews_client.settings, "google_reviews_client_id", "test-client-id")
    monkeypatch.setattr(google_reviews_client.settings, "google_reviews_client_secret", "test-client-secret")
    monkeypatch.setattr(google_reviews_client.settings, "google_reviews_refresh_token", "test-refresh-token")
    monkeypatch.setattr(google_reviews_client.settings, "google_reviews_account_id", "123")
    monkeypatch.setattr(google_reviews_client.settings, "google_reviews_location_id", "456")
    monkeypatch.setattr(google_reviews_client.Credentials, "refresh", lambda self, request: None)
    return GoogleReviewsClient()


def _patch_get(monkeypatch, *responses: dict) -> _FakeCall:
    fake = _FakeCall([_FakeResponse(r) for r in responses])
    monkeypatch.setattr(google_reviews_client.requests, "get", fake)
    return fake


def _patch_put(monkeypatch, response: dict, status_code: int = 200) -> _FakeCall:
    fake = _FakeCall([_FakeResponse(response, status_code)])
    monkeypatch.setattr(google_reviews_client.requests, "put", fake)
    return fake


_ONE_REVIEW = {
    "reviewId": "r1",
    "reviewer": {"displayName": "Alex R."},
    "starRating": "FIVE",
    "comment": "Fantastic experience!",
    "createTime": "2024-08-13T09:00:00Z",
}


@pytest.mark.asyncio
async def test_fetch_reviews_parses_star_rating_and_fields(monkeypatch):
    client = _configure_credentials(monkeypatch)
    _patch_get(monkeypatch, {"reviews": [_ONE_REVIEW]})

    reviews = await client.fetch_reviews()

    assert len(reviews) == 1
    review = reviews[0]
    assert review.external_id == "r1"
    assert review.platform == "google"
    assert review.customer_name == "Alex R."
    assert review.rating == 5
    assert review.text == "Fantastic experience!"
    assert review.review_date == datetime(2024, 8, 13, 9, 0, tzinfo=timezone.utc)


@pytest.mark.asyncio
async def test_fetch_reviews_maps_every_star_rating_value(monkeypatch):
    client = _configure_credentials(monkeypatch)
    ratings = ["ONE", "TWO", "THREE", "FOUR", "FIVE", "STAR_RATING_UNSPECIFIED"]
    reviews_payload = [
        {**_ONE_REVIEW, "reviewId": f"r{i}", "starRating": rating} for i, rating in enumerate(ratings)
    ]
    _patch_get(monkeypatch, {"reviews": reviews_payload})

    reviews = await client.fetch_reviews()

    # Last one (STAR_RATING_UNSPECIFIED) maps to None, not 0 -- a genuine
    # "no rating given" stays distinguishable from a real 0 rating.
    assert [r.rating for r in reviews] == [1, 2, 3, 4, 5, None]


@pytest.mark.asyncio
async def test_fetch_reviews_follows_pagination(monkeypatch):
    client = _configure_credentials(monkeypatch)
    fake_get = _patch_get(
        monkeypatch,
        {"reviews": [{**_ONE_REVIEW, "reviewId": "r1"}], "nextPageToken": "page-2"},
        {"reviews": [{**_ONE_REVIEW, "reviewId": "r2"}]},
    )

    reviews = await client.fetch_reviews()

    assert [r.external_id for r in reviews] == ["r1", "r2"]
    assert len(fake_get.calls) == 2
    assert fake_get.calls[1][1]["params"] == {"pageToken": "page-2"}


@pytest.mark.asyncio
async def test_fetch_reviews_filters_by_since(monkeypatch):
    client = _configure_credentials(monkeypatch)
    older = {**_ONE_REVIEW, "reviewId": "old", "createTime": "2020-01-01T00:00:00Z"}
    newer = {**_ONE_REVIEW, "reviewId": "new", "createTime": "2024-08-13T09:00:00Z"}
    _patch_get(monkeypatch, {"reviews": [older, newer]})

    reviews = await client.fetch_reviews(since=datetime(2024, 1, 1, tzinfo=timezone.utc))

    assert [r.external_id for r in reviews] == ["new"]


@pytest.mark.asyncio
async def test_fetch_reviews_correct_url(monkeypatch):
    client = _configure_credentials(monkeypatch)
    fake_get = _patch_get(monkeypatch, {"reviews": []})

    await client.fetch_reviews()

    assert fake_get.last_url == (
        "https://mybusiness.googleapis.com/v4/accounts/123/locations/456/reviews"
    )
    assert "Bearer" in fake_get.last_kwargs["headers"]["Authorization"]


@pytest.mark.asyncio
async def test_get_review_returns_none_on_404(monkeypatch):
    client = _configure_credentials(monkeypatch)
    monkeypatch.setattr(
        google_reviews_client.requests, "get", lambda url, **kwargs: _FakeResponse({}, status_code=404)
    )

    review = await client.get_review("does-not-exist")

    assert review is None


@pytest.mark.asyncio
async def test_get_review_returns_parsed_review(monkeypatch):
    client = _configure_credentials(monkeypatch)
    _patch_get(monkeypatch, _ONE_REVIEW)

    review = await client.get_review("r1")

    assert review.external_id == "r1"
    assert review.rating == 5


@pytest.mark.asyncio
async def test_publish_reply_sends_put_with_comment_body(monkeypatch):
    client = _configure_credentials(monkeypatch)
    fake_put = _patch_put(monkeypatch, {"comment": "Thank you!"})

    await client.publish_reply("r1", "Thank you!")

    assert fake_put.last_url == (
        "https://mybusiness.googleapis.com/v4/accounts/123/locations/456/reviews/r1/reply"
    )
    assert fake_put.last_kwargs["json"] == {"comment": "Thank you!"}


@pytest.mark.asyncio
async def test_publish_reply_raises_on_api_error(monkeypatch):
    client = _configure_credentials(monkeypatch)
    _patch_put(monkeypatch, {"error": {"message": "denied"}}, status_code=403)

    with pytest.raises(GoogleReviewsError, match="reply failed"):
        await client.publish_reply("r1", "Thank you!")


@pytest.mark.asyncio
async def test_fetch_reviews_raises_when_not_configured(monkeypatch):
    monkeypatch.setattr(google_reviews_client.settings, "google_reviews_client_id", "")
    monkeypatch.setattr(google_reviews_client.settings, "google_reviews_client_secret", "")
    monkeypatch.setattr(google_reviews_client.settings, "google_reviews_refresh_token", "")
    client = GoogleReviewsClient()

    with pytest.raises(GoogleReviewsError, match="isn't connected yet"):
        await client.fetch_reviews()


@pytest.mark.asyncio
async def test_fetch_reviews_times_out_fast_instead_of_hanging(monkeypatch):
    client = _configure_credentials(monkeypatch)
    monkeypatch.setattr(google_reviews_client, "_CALL_TIMEOUT_SECONDS", 0.05)

    def _never_returns(url, **kwargs):
        import time

        time.sleep(0.5)

    monkeypatch.setattr(google_reviews_client.requests, "get", _never_returns)

    with pytest.raises(GoogleReviewsError, match="didn't respond"):
        await client.fetch_reviews()


# --- GoogleReviewsPlatform (the ReviewPlatform/ReviewResponsePublisher adapter) ---


@pytest.mark.asyncio
async def test_platform_publish_response_returns_published_on_success(monkeypatch):
    client = _configure_credentials(monkeypatch)
    _patch_put(monkeypatch, {"comment": "Thanks!"})
    platform = GoogleReviewsPlatform(client=client)

    result = await platform.publish_response("r1", "Thanks!")

    assert result.status == "published"
    assert result.platform_response_id == "r1"


@pytest.mark.asyncio
async def test_platform_publish_response_returns_error_result_not_raising(monkeypatch):
    """This is the one method review_service could call automatically post-
    approval (see this agent's CLAUDE.md "Human approval") -- a failed
    publish must come back as data the caller can show the user, not an
    unhandled exception."""
    monkeypatch.setattr(google_reviews_client.settings, "google_reviews_client_id", "")
    monkeypatch.setattr(google_reviews_client.settings, "google_reviews_client_secret", "")
    monkeypatch.setattr(google_reviews_client.settings, "google_reviews_refresh_token", "")
    platform = GoogleReviewsPlatform(client=GoogleReviewsClient())

    result = await platform.publish_response("r1", "Thanks!")

    assert result.status == "error"
    assert "isn't connected yet" in result.error
