"""Tests for GET /api/public/articles (the list endpoint) -- consumed by
Astro's blog index page at build time. Per-slug behavior (draft hidden,
published visible) is covered in test_admin_articles_api.py alongside the
publish flow that produces those states.
"""
from app.core.config import settings


def _make_admin(monkeypatch, email: str):
    monkeypatch.setattr(settings, "platform_admin_emails", email)


def test_list_public_articles_requires_no_auth(client):
    resp = client.get("/api/public/articles")
    assert resp.status_code == 200
    assert resp.json() == {"items": [], "total": 0}


def test_list_public_articles_excludes_drafts_and_includes_published(client, business, monkeypatch):
    _make_admin(monkeypatch, business["email"])
    client.post(
        "/api/admin/articles",
        json={"title": "Draft Article", "slug": "draft-article", "content": "<p>Draft</p>"},
        headers=business["headers"],
    )
    published_resp = client.post(
        "/api/admin/articles",
        json={"title": "Published Article", "slug": "published-article", "content": "<p>Live</p>"},
        headers=business["headers"],
    )
    article_id = published_resp.json()["id"]
    client.post(f"/api/admin/articles/{article_id}/publish", headers=business["headers"])

    resp = client.get("/api/public/articles")
    assert resp.status_code == 200
    body = resp.json()
    assert body["total"] == 1
    slugs = {item["slug"] for item in body["items"]}
    assert slugs == {"published-article"}
