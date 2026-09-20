"""SEO Audit & Optimization -- Stage 1 (website registration) tests. See
apps/agents/seo-audit/CLAUDE.md. Real DNS resolution is mocked out for
tests that aren't specifically exercising the SSRF guard itself, same
pattern test_web_crawl.py already uses for the shared crawler layer.
"""
from app.services import seo_website_service, web_crawl


def _entitle(business, grant_agent):
    grant_agent(business["business_id"], "seo_audit_optimization")


def _stub_public_url(monkeypatch):
    monkeypatch.setattr(seo_website_service.web_crawl, "assert_public_url", lambda url: None)


def test_create_website_requires_entitlement(client, business, monkeypatch):
    _stub_public_url(monkeypatch)
    resp = client.post(
        "/api/agents/seo/websites", json={"url": "https://example.com"}, headers=business["headers"]
    )
    assert resp.status_code == 403


def test_create_website_succeeds_once_entitled(client, business, grant_agent, monkeypatch):
    _entitle(business, grant_agent)
    _stub_public_url(monkeypatch)

    resp = client.post(
        "/api/agents/seo/websites",
        json={
            "url": "https://example.com",
            "name": "Example Co",
            "target_country": "NO",
            "target_language": "en",
            "primary_category": "software",
            "target_keywords": ["ai chatbot", "seo audit tool"],
            "crawl_tier": "standard",
        },
        headers=business["headers"],
    )

    assert resp.status_code == 200
    body = resp.json()
    assert body["url"] == "https://example.com"
    assert body["name"] == "Example Co"
    assert body["crawl_tier"] == "standard"
    assert body["target_keywords"] == ["ai chatbot", "seo audit tool"]


def test_create_website_defaults_to_starter_tier(client, business, grant_agent, monkeypatch):
    _entitle(business, grant_agent)
    _stub_public_url(monkeypatch)

    resp = client.post("/api/agents/seo/websites", json={"url": "https://example.com"}, headers=business["headers"])

    assert resp.json()["crawl_tier"] == "starter"


def test_create_website_rejects_invalid_crawl_tier(client, business, grant_agent, monkeypatch):
    _entitle(business, grant_agent)
    _stub_public_url(monkeypatch)

    resp = client.post(
        "/api/agents/seo/websites",
        json={"url": "https://example.com", "crawl_tier": "enterprise"},
        headers=business["headers"],
    )

    assert resp.status_code == 400


def test_create_website_rejects_non_http_scheme(client, business, grant_agent):
    """Not mocking _assert_public_url here -- a bad scheme is rejected
    before any DNS resolution happens, so this is deterministic without
    network access."""
    _entitle(business, grant_agent)

    resp = client.post(
        "/api/agents/seo/websites", json={"url": "ftp://example.com"}, headers=business["headers"]
    )

    assert resp.status_code == 400


def test_create_website_rejects_a_private_ip_target(client, business, grant_agent, monkeypatch):
    _entitle(business, grant_agent)
    monkeypatch.setattr(web_crawl.socket, "gethostbyname", lambda host: "127.0.0.1")

    resp = client.post(
        "/api/agents/seo/websites", json={"url": "https://internal.example"}, headers=business["headers"]
    )

    assert resp.status_code == 400


def test_website_limit_is_enforced(client, business, grant_agent, monkeypatch):
    _entitle(business, grant_agent)
    _stub_public_url(monkeypatch)
    monkeypatch.setattr(seo_website_service, "DEFAULT_SEO_WEBSITE_LIMIT", 2)

    for i in range(2):
        resp = client.post(
            "/api/agents/seo/websites", json={"url": f"https://example{i}.com"}, headers=business["headers"]
        )
        assert resp.status_code == 200

    resp = client.post("/api/agents/seo/websites", json={"url": "https://one-too-many.com"}, headers=business["headers"])
    assert resp.status_code == 402


def test_website_limit_override_raises_the_cap(client, business, grant_agent, monkeypatch, db_session):
    from app.models.business import Business

    _entitle(business, grant_agent)
    _stub_public_url(monkeypatch)
    monkeypatch.setattr(seo_website_service, "DEFAULT_SEO_WEBSITE_LIMIT", 1)

    biz = db_session.query(Business).filter(Business.id == business["business_id"]).first()
    biz.seo_website_limit_override = 3
    db_session.commit()

    for i in range(3):
        resp = client.post(
            "/api/agents/seo/websites", json={"url": f"https://example{i}.com"}, headers=business["headers"]
        )
        assert resp.status_code == 200


def test_list_websites_scoped_to_business(client, business, signup, grant_agent, monkeypatch):
    _entitle(business, grant_agent)
    other = signup()
    grant_agent(other["business_id"], "seo_audit_optimization")
    _stub_public_url(monkeypatch)

    client.post("/api/agents/seo/websites", json={"url": "https://mine.example.com"}, headers=business["headers"])
    client.post("/api/agents/seo/websites", json={"url": "https://theirs.example.com"}, headers=other["headers"])

    resp = client.get("/api/agents/seo/websites", headers=business["headers"])

    assert resp.status_code == 200
    urls = [w["url"] for w in resp.json()]
    assert urls == ["https://mine.example.com"]


def test_get_unknown_website_404s(client, business, grant_agent):
    _entitle(business, grant_agent)
    resp = client.get(
        "/api/agents/seo/websites/00000000-0000-0000-0000-000000000000", headers=business["headers"]
    )
    assert resp.status_code == 404


def test_cannot_get_another_businesss_website(client, business, signup, grant_agent, monkeypatch):
    _entitle(business, grant_agent)
    other = signup()
    grant_agent(other["business_id"], "seo_audit_optimization")
    _stub_public_url(monkeypatch)

    create_resp = client.post(
        "/api/agents/seo/websites", json={"url": "https://theirs.example.com"}, headers=other["headers"]
    )
    website_id = create_resp.json()["id"]

    resp = client.get(f"/api/agents/seo/websites/{website_id}", headers=business["headers"])
    assert resp.status_code == 404


def test_delete_website_removes_it(client, business, grant_agent, monkeypatch):
    _entitle(business, grant_agent)
    _stub_public_url(monkeypatch)

    create_resp = client.post(
        "/api/agents/seo/websites", json={"url": "https://example.com"}, headers=business["headers"]
    )
    website_id = create_resp.json()["id"]

    resp = client.delete(f"/api/agents/seo/websites/{website_id}", headers=business["headers"])
    assert resp.status_code == 204

    resp = client.get(f"/api/agents/seo/websites/{website_id}", headers=business["headers"])
    assert resp.status_code == 404


def test_cannot_delete_another_businesss_website(client, business, signup, grant_agent, monkeypatch):
    _entitle(business, grant_agent)
    other = signup()
    grant_agent(other["business_id"], "seo_audit_optimization")
    _stub_public_url(monkeypatch)

    create_resp = client.post(
        "/api/agents/seo/websites", json={"url": "https://theirs.example.com"}, headers=other["headers"]
    )
    website_id = create_resp.json()["id"]

    resp = client.delete(f"/api/agents/seo/websites/{website_id}", headers=business["headers"])
    assert resp.status_code == 404
