"""QA 2026-10-02 (D3/M4, D8): one entry per site, and the site the widget runs
on counts toward the plan's websites without being added by hand."""

import pytest

from app.services import chat_service
from app.services.website_service import normalize_domain


@pytest.mark.parametrize(
    "raw",
    ["mielikkix.ai", "https://mielikkix.ai", "https://mielikkix.ai/", "HTTPS://WWW.Mielikkix.ai/pricing/?x=1", "mielikkix.ai:443"],
)
def test_normalize_domain_gives_one_form(raw):
    assert normalize_domain(raw) == "mielikkix.ai"


def test_adding_the_same_site_twice_is_rejected(client, business):
    first = client.post("/api/websites", json={"domain": "https://shop.example/"}, headers=business["headers"])
    assert first.status_code == 200 and first.json()["domain"] == "shop.example"
    again = client.post("/api/websites", json={"domain": "shop.example"}, headers=business["headers"])
    assert again.status_code == 409


async def _fake_run_rag(**kwargs):
    return "a reply", "faq", 0.9


def _chat(client, business, session, origin):
    return client.post(
        "/api/chat/message",
        json={"business_id": business["business_id"], "session_id": session, "message": "hello"},
        headers={"Origin": origin},
    )


def test_widget_site_is_registered_once_from_the_origin(client, business, monkeypatch):
    monkeypatch.setattr(chat_service, "run_rag", _fake_run_rag)

    assert _chat(client, business, "s1", "https://www.my-cafe.example").status_code == 200
    _chat(client, business, "s2", "https://my-cafe.example")
    _chat(client, business, "s3", "http://localhost:4321")

    sites = client.get("/api/websites", headers=business["headers"]).json()
    assert [s["domain"] for s in sites] == ["my-cafe.example"]


def test_widget_site_over_the_limit_is_skipped_but_chat_still_works(client, business, monkeypatch):
    monkeypatch.setattr(chat_service, "run_rag", _fake_run_rag)
    client.post("/api/websites", json={"domain": "first.example"}, headers=business["headers"])  # Free plan: 1 site

    resp = _chat(client, business, "s1", "https://second.example")

    assert resp.status_code == 200
    assert [s["domain"] for s in client.get("/api/websites", headers=business["headers"]).json()] == ["first.example"]
