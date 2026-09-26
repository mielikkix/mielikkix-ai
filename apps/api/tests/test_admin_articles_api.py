"""API-level tests for Mielikkix Admin -> Articles (app/api/admin_articles.py).

Pure CRUD/publish-state logic is covered by test_article_service.py; this
file covers authorization (the actual non-negotiable requirement -- only
require_platform_admin, never hidden-nav-only) and the HTTP surface.

Deployment model (2026-09-20 decision -- manual Hostinger deployment, no
automatic build/upload): publish/unpublish here ONLY ever touch the
database (status + deployment_status="pending") and never call
deploy_service at all anymore -- see article_service.py's own module
docstring. The tests below for deploy_service.run_deploy() exercise that
function directly (it's kept as dormant, reusable code for whenever real
Hostinger credentials exist and auto-deploy is wanted again), not through
the publish/unpublish HTTP routes, which no longer invoke it.
"""
import pytest

from app.core.config import settings
from app.services import deploy_service


def _make_admin(monkeypatch, email: str):
    monkeypatch.setattr(settings, "platform_admin_emails", email)


def _article_payload(**overrides):
    payload = {"title": "Test Article", "content": "<p>Hello world</p>"}
    payload.update(overrides)
    return payload


# ---------------------------------------------------------------------------
# Authorization
# ---------------------------------------------------------------------------

def test_unauthenticated_cannot_list_articles(client):
    resp = client.get("/api/admin/articles")
    assert resp.status_code == 401


def test_business_owner_cannot_list_articles(client, business):
    resp = client.get("/api/admin/articles", headers=business["headers"])
    assert resp.status_code == 403


def test_business_owner_cannot_create_article(client, business):
    resp = client.post("/api/admin/articles", json=_article_payload(), headers=business["headers"])
    assert resp.status_code == 403


def test_business_owner_cannot_publish_article(client, business, db_session, monkeypatch):
    # Create the article as an admin first, then confirm a DIFFERENT,
    # non-admin business cannot publish it.
    _make_admin(monkeypatch, business["email"])
    create_resp = client.post("/api/admin/articles", json=_article_payload(), headers=business["headers"])
    article_id = create_resp.json()["id"]

    monkeypatch.setattr(settings, "platform_admin_emails", "someone-else@mielikkix.ai")
    resp = client.post(f"/api/admin/articles/{article_id}/publish", headers=business["headers"])
    assert resp.status_code == 403


def test_business_owner_cannot_call_public_article_api_to_bypass_admin_auth(client, business):
    # Sanity check that the public API itself (no auth at all) is separate
    # from admin auth -- it simply never exposes drafts, regardless of who calls it.
    resp = client.get("/api/public/articles/does-not-exist", headers=business["headers"])
    assert resp.status_code == 404


def test_platform_admin_can_list_articles(client, business, monkeypatch):
    _make_admin(monkeypatch, business["email"])
    resp = client.get("/api/admin/articles", headers=business["headers"])
    assert resp.status_code == 200
    assert resp.json()["items"] == []


# ---------------------------------------------------------------------------
# Articles CRUD
# ---------------------------------------------------------------------------

def test_admin_can_create_draft(client, business, monkeypatch):
    _make_admin(monkeypatch, business["email"])
    resp = client.post("/api/admin/articles", json=_article_payload(), headers=business["headers"])
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "draft"
    assert body["slug"] == "test-article"
    assert body["author"]["email"] == business["email"]


def test_admin_can_edit_draft(client, business, monkeypatch):
    _make_admin(monkeypatch, business["email"])
    create_resp = client.post("/api/admin/articles", json=_article_payload(), headers=business["headers"])
    article_id = create_resp.json()["id"]

    resp = client.patch(
        f"/api/admin/articles/{article_id}", json={"title": "Updated Title"}, headers=business["headers"]
    )
    assert resp.status_code == 200
    assert resp.json()["title"] == "Updated Title"


def test_create_article_rejects_duplicate_slug(client, business, monkeypatch):
    _make_admin(monkeypatch, business["email"])
    client.post("/api/admin/articles", json=_article_payload(slug="same-slug"), headers=business["headers"])
    resp = client.post(
        "/api/admin/articles", json=_article_payload(title="Different Title", slug="same-slug"),
        headers=business["headers"],
    )
    assert resp.status_code == 409


# ---------------------------------------------------------------------------
# Publish / unpublish -- database-only, manual deployment
# ---------------------------------------------------------------------------

def test_publish_marks_status_published_but_not_live(client, business, monkeypatch):
    _make_admin(monkeypatch, business["email"])
    create_resp = client.post("/api/admin/articles", json=_article_payload(), headers=business["headers"])
    article_id = create_resp.json()["id"]

    resp = client.post(f"/api/admin/articles/{article_id}/publish", headers=business["headers"])
    assert resp.status_code == 200
    body = resp.json()
    assert body["article"]["status"] == "published"
    assert body["article"]["published_at"] is not None
    assert body["article"]["deployment_status"] == "pending"
    assert body["article"]["deployment_status"] != "live"


def test_publish_does_not_call_deploy_service_at_all(client, business, monkeypatch):
    """Regression guard for the 2026-09-20 manual-deployment decision --
    Publish must be a pure, fast database write. If anything on the
    publish path ever calls deploy_service.run_deploy again (e.g. a future
    change reintroducing an automatic BackgroundTasks trigger), this test
    fails immediately rather than silently reverting to the old
    behavior."""
    calls = []
    monkeypatch.setattr(deploy_service, "run_deploy", lambda article_id: calls.append(article_id))
    _make_admin(monkeypatch, business["email"])
    create_resp = client.post("/api/admin/articles", json=_article_payload(), headers=business["headers"])
    article_id = create_resp.json()["id"]

    client.post(f"/api/admin/articles/{article_id}/publish", headers=business["headers"])

    assert calls == []


def test_deploy_service_run_deploy_reports_honest_failure_when_unconfigured(client, business, monkeypatch, db_session):
    """deploy_service.run_deploy is kept as dormant, reusable code (see its
    own module docstring) for whenever real Hostinger credentials exist --
    it's no longer called automatically by publish/unpublish, but must
    still behave correctly when invoked directly."""
    monkeypatch.setattr(deploy_service, "SessionLocal", lambda: db_session)
    _make_admin(monkeypatch, business["email"])
    create_resp = client.post("/api/admin/articles", json=_article_payload(), headers=business["headers"])
    article_id = create_resp.json()["id"]
    client.post(f"/api/admin/articles/{article_id}/publish", headers=business["headers"])

    deploy_service.run_deploy(article_id)

    detail = client.get(f"/api/admin/articles/{article_id}", headers=business["headers"]).json()
    assert detail["deployment_status"] == "failed"
    assert "WEBSITE_REPO_PATH" in detail["last_deployment_error"]


def test_deployment_error_never_contains_configured_secrets(client, business, monkeypatch, db_session):
    monkeypatch.setattr(settings, "website_repo_path", "/nonexistent/path")
    monkeypatch.setattr(settings, "website_deploy_sftp_host", "sftp.example.com")
    monkeypatch.setattr(settings, "website_deploy_sftp_username", "deployuser")
    monkeypatch.setattr(settings, "website_deploy_sftp_password", "super-secret-password-value")
    monkeypatch.setattr(settings, "website_deploy_remote_path", "/public_html")
    monkeypatch.setattr(deploy_service, "SessionLocal", lambda: db_session)
    _make_admin(monkeypatch, business["email"])

    create_resp = client.post("/api/admin/articles", json=_article_payload(), headers=business["headers"])
    article_id = create_resp.json()["id"]
    client.post(f"/api/admin/articles/{article_id}/publish", headers=business["headers"])

    deploy_service.run_deploy(article_id)

    detail = client.get(f"/api/admin/articles/{article_id}", headers=business["headers"]).json()
    assert "super-secret-password-value" not in (detail["last_deployment_error"] or "")


def test_unpublish_reverts_status_to_draft(client, business, monkeypatch):
    _make_admin(monkeypatch, business["email"])
    create_resp = client.post("/api/admin/articles", json=_article_payload(), headers=business["headers"])
    article_id = create_resp.json()["id"]
    client.post(f"/api/admin/articles/{article_id}/publish", headers=business["headers"])

    resp = client.post(f"/api/admin/articles/{article_id}/unpublish", headers=business["headers"])
    assert resp.status_code == 200
    assert resp.json()["article"]["status"] == "draft"


def test_unpublish_does_not_call_deploy_service_at_all(client, business, monkeypatch):
    _make_admin(monkeypatch, business["email"])
    create_resp = client.post("/api/admin/articles", json=_article_payload(), headers=business["headers"])
    article_id = create_resp.json()["id"]
    client.post(f"/api/admin/articles/{article_id}/publish", headers=business["headers"])

    calls = []
    monkeypatch.setattr(deploy_service, "run_deploy", lambda article_id: calls.append(article_id))
    client.post(f"/api/admin/articles/{article_id}/unpublish", headers=business["headers"])

    assert calls == []


# ---------------------------------------------------------------------------
# Manual deployment confirmation (POST .../deployment-result)
# ---------------------------------------------------------------------------

def test_unauthenticated_cannot_confirm_deployment(client):
    resp = client.post("/api/admin/articles/00000000-0000-0000-0000-000000000000/deployment-result", json={"success": True})
    assert resp.status_code == 401


def test_business_owner_cannot_confirm_deployment(client, business, monkeypatch):
    _make_admin(monkeypatch, business["email"])
    create_resp = client.post("/api/admin/articles", json=_article_payload(), headers=business["headers"])
    article_id = create_resp.json()["id"]
    client.post(f"/api/admin/articles/{article_id}/publish", headers=business["headers"])

    monkeypatch.setattr(settings, "platform_admin_emails", "someone-else@mielikkix.ai")
    resp = client.post(
        f"/api/admin/articles/{article_id}/deployment-result", json={"success": True}, headers=business["headers"]
    )
    assert resp.status_code == 403


def test_platform_admin_can_confirm_successful_manual_deployment(client, business, monkeypatch):
    _make_admin(monkeypatch, business["email"])
    create_resp = client.post("/api/admin/articles", json=_article_payload(), headers=business["headers"])
    article_id = create_resp.json()["id"]
    client.post(f"/api/admin/articles/{article_id}/publish", headers=business["headers"])

    resp = client.post(
        f"/api/admin/articles/{article_id}/deployment-result", json={"success": True}, headers=business["headers"]
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["deployment_status"] == "live"
    assert body["last_deployed_at"] is not None
    assert body["last_deployment_error"] is None


def test_platform_admin_can_report_manual_deployment_failure(client, business, monkeypatch):
    _make_admin(monkeypatch, business["email"])
    create_resp = client.post("/api/admin/articles", json=_article_payload(), headers=business["headers"])
    article_id = create_resp.json()["id"]
    client.post(f"/api/admin/articles/{article_id}/publish", headers=business["headers"])

    resp = client.post(
        f"/api/admin/articles/{article_id}/deployment-result",
        json={"success": False, "message": "Upload to Hostinger timed out."},
        headers=business["headers"],
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["deployment_status"] == "failed"
    assert body["last_deployment_error"] == "Upload to Hostinger timed out."


def test_confirming_deployment_for_unknown_article_404s(client, business, monkeypatch):
    _make_admin(monkeypatch, business["email"])
    resp = client.post(
        "/api/admin/articles/00000000-0000-0000-0000-000000000000/deployment-result",
        json={"success": True},
        headers=business["headers"],
    )
    assert resp.status_code == 404


def test_deployment_result_response_never_contains_admin_provided_message_as_a_credential_field(client, business, monkeypatch):
    """Not a secret-detection test (there's no reliable way to redact an
    admin's own typed text) -- just confirms the endpoint stores and
    returns exactly what was sent, nothing fabricated or substituted."""
    _make_admin(monkeypatch, business["email"])
    create_resp = client.post("/api/admin/articles", json=_article_payload(), headers=business["headers"])
    article_id = create_resp.json()["id"]
    client.post(f"/api/admin/articles/{article_id}/publish", headers=business["headers"])

    resp = client.post(
        f"/api/admin/articles/{article_id}/deployment-result",
        json={"success": False, "message": "sftp connection refused"},
        headers=business["headers"],
    )
    assert resp.json()["last_deployment_error"] == "sftp connection refused"


def test_draft_article_not_publicly_accessible(client, business, monkeypatch):
    _make_admin(monkeypatch, business["email"])
    create_resp = client.post("/api/admin/articles", json=_article_payload(slug="still-a-draft"), headers=business["headers"])

    resp = client.get("/api/public/articles/still-a-draft")
    assert resp.status_code == 404


def test_published_article_publicly_accessible(client, business, monkeypatch):
    _make_admin(monkeypatch, business["email"])
    create_resp = client.post(
        "/api/admin/articles", json=_article_payload(slug="now-published"), headers=business["headers"]
    )
    article_id = create_resp.json()["id"]
    client.post(f"/api/admin/articles/{article_id}/publish", headers=business["headers"])

    resp = client.get("/api/public/articles/now-published")
    assert resp.status_code == 200
    body = resp.json()
    assert body["slug"] == "now-published"
    # Never leaks admin-only fields
    assert "deployment_status" not in body
    assert "last_deployment_error" not in body


# ---------------------------------------------------------------------------
# Permanent deletion (DELETE /api/admin/articles/{id})
# ---------------------------------------------------------------------------

def test_unauthenticated_cannot_delete_article(client):
    resp = client.delete("/api/admin/articles/00000000-0000-0000-0000-000000000000")
    assert resp.status_code == 401


def test_business_owner_cannot_delete_article(client, business, monkeypatch):
    _make_admin(monkeypatch, business["email"])
    create_resp = client.post("/api/admin/articles", json=_article_payload(), headers=business["headers"])
    article_id = create_resp.json()["id"]

    monkeypatch.setattr(settings, "platform_admin_emails", "someone-else@mielikkix.ai")
    resp = client.delete(f"/api/admin/articles/{article_id}", headers=business["headers"])
    assert resp.status_code == 403

    # Confirm the article genuinely survived the rejected attempt -- switch
    # back to admin and check.
    _make_admin(monkeypatch, business["email"])
    get_resp = client.get(f"/api/admin/articles/{article_id}", headers=business["headers"])
    assert get_resp.status_code == 200


def test_deleting_unknown_article_404s(client, business, monkeypatch):
    _make_admin(monkeypatch, business["email"])
    resp = client.delete("/api/admin/articles/00000000-0000-0000-0000-000000000000", headers=business["headers"])
    assert resp.status_code == 404


def test_platform_admin_can_permanently_delete_an_article(client, business, monkeypatch):
    _make_admin(monkeypatch, business["email"])
    create_resp = client.post(
        "/api/admin/articles", json=_article_payload(slug="to-be-deleted"), headers=business["headers"]
    )
    article_id = create_resp.json()["id"]
    client.post(f"/api/admin/articles/{article_id}/publish", headers=business["headers"])

    # Exists everywhere before deletion.
    assert client.get(f"/api/admin/articles/{article_id}", headers=business["headers"]).status_code == 200
    assert client.get("/api/public/articles/to-be-deleted").status_code == 200

    resp = client.delete(f"/api/admin/articles/{article_id}", headers=business["headers"])
    assert resp.status_code == 204
    assert resp.content == b""

    # Gone from the admin API (a real deletion, not a status flip to draft).
    assert client.get(f"/api/admin/articles/{article_id}", headers=business["headers"]).status_code == 404

    # Gone from the admin list.
    list_body = client.get("/api/admin/articles", headers=business["headers"]).json()
    assert article_id not in {item["id"] for item in list_body["items"]}

    # Gone from the public API, both by slug and in the listing.
    assert client.get("/api/public/articles/to-be-deleted").status_code == 404
    public_list = client.get("/api/public/articles").json()
    assert "to-be-deleted" not in {item["slug"] for item in public_list["items"]}


def test_deleting_an_article_does_not_delete_or_modify_its_author(client, business, db_session, monkeypatch):
    from app.models.user import User

    _make_admin(monkeypatch, business["email"])
    create_resp = client.post("/api/admin/articles", json=_article_payload(), headers=business["headers"])
    article_id = create_resp.json()["id"]
    author_id = create_resp.json()["author"]["id"]

    client.delete(f"/api/admin/articles/{article_id}", headers=business["headers"])

    author = db_session.query(User).filter(User.id == author_id).first()
    assert author is not None
    assert author.email == business["email"]
    assert author.is_active is True


def test_failed_deletion_does_not_remove_the_article(client, business, monkeypatch):
    """Simulates a mid-operation failure (e.g. a DB error) -- the article
    must survive, not be left in some half-deleted state."""
    from app.services import article_service

    _make_admin(monkeypatch, business["email"])
    create_resp = client.post("/api/admin/articles", json=_article_payload(), headers=business["headers"])
    article_id = create_resp.json()["id"]

    def _boom(db, article_id_arg):
        raise RuntimeError("simulated database failure")

    monkeypatch.setattr(article_service, "delete_article", _boom)
    with pytest.raises(RuntimeError):
        client.delete(f"/api/admin/articles/{article_id}", headers=business["headers"])

    monkeypatch.undo()
    _make_admin(monkeypatch, business["email"])
    get_resp = client.get(f"/api/admin/articles/{article_id}", headers=business["headers"])
    assert get_resp.status_code == 200


# ---------------------------------------------------------------------------
# Regression: publish/unpublish/deployment-status/public behavior still work
# alongside the new delete endpoint (deleting one article must never affect
# another).
# ---------------------------------------------------------------------------

def test_deleting_one_article_does_not_affect_another(client, business, monkeypatch):
    _make_admin(monkeypatch, business["email"])
    keep_resp = client.post(
        "/api/admin/articles", json=_article_payload(title="Keep Me", slug="keep-me"), headers=business["headers"]
    )
    keep_id = keep_resp.json()["id"]
    client.post(f"/api/admin/articles/{keep_id}/publish", headers=business["headers"])

    delete_resp = client.post(
        "/api/admin/articles", json=_article_payload(title="Delete Me", slug="delete-me"), headers=business["headers"]
    )
    delete_id = delete_resp.json()["id"]

    client.delete(f"/api/admin/articles/{delete_id}", headers=business["headers"])

    # The kept article's publish/deployment behavior is completely unaffected.
    assert client.get(f"/api/admin/articles/{keep_id}", headers=business["headers"]).json()["status"] == "published"
    deploy_resp = client.post(
        f"/api/admin/articles/{keep_id}/deployment-result", json={"success": True}, headers=business["headers"]
    )
    assert deploy_resp.json()["deployment_status"] == "live"
    assert client.get("/api/public/articles/keep-me").status_code == 200
