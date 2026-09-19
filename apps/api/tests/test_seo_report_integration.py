"""Integration tests for Stage 11 (apps/agents/seo-copywriter/CLAUDE.md):
the GET .../audits/{id}/report HTTP endpoint. Pure assembly logic is
covered by test_seo_report_service.py; this file covers entitlement,
404/400s, and cross-business isolation.
"""
from app.models.seo_audit import SeoFinding


def _entitle(business, grant_agent):
    grant_agent(business["business_id"], "seo_audit_optimization")


def _stub_public_url(monkeypatch):
    from app.services import seo_website_service
    monkeypatch.setattr(seo_website_service.web_crawl, "assert_public_url", lambda url: None)


def test_report_requires_entitlement(client, business):
    resp = client.get(
        "/api/agents/seo/audits/00000000-0000-0000-0000-000000000000/report", headers=business["headers"]
    )
    assert resp.status_code == 403


def test_report_404s_for_unknown_audit(client, business, grant_agent):
    _entitle(business, grant_agent)
    resp = client.get(
        "/api/agents/seo/audits/00000000-0000-0000-0000-000000000000/report", headers=business["headers"]
    )
    assert resp.status_code == 404


def test_report_400s_for_a_pending_audit(client, business, grant_agent, monkeypatch):
    _entitle(business, grant_agent)
    _stub_public_url(monkeypatch)
    create_resp = client.post("/api/agents/seo/websites", json={"url": "https://greenleaf.test"}, headers=business["headers"])
    website_id = create_resp.json()["id"]
    audit_resp = client.post(f"/api/agents/seo/websites/{website_id}/audits", headers=business["headers"])
    audit_id = audit_resp.json()["id"]  # BackgroundTasks never actually ran in TestClient -> still "pending"

    resp = client.get(f"/api/agents/seo/audits/{audit_id}/report", headers=business["headers"])
    assert resp.status_code == 400


def test_report_returns_real_assembled_data(client, business, grant_agent, monkeypatch, db_session):
    _entitle(business, grant_agent)
    _stub_public_url(monkeypatch)
    create_resp = client.post("/api/agents/seo/websites", json={"url": "https://greenleaf.test"}, headers=business["headers"])
    website_id = create_resp.json()["id"]
    audit_resp = client.post(f"/api/agents/seo/websites/{website_id}/audits", headers=business["headers"])
    audit_id = audit_resp.json()["id"]

    from app.models.seo_audit import SeoAudit
    audit = db_session.query(SeoAudit).filter(SeoAudit.id == audit_id).first()
    audit.status = "completed"
    audit.health_on_page = 80
    audit.executive_summary = "Fix missing titles first."
    db_session.add(SeoFinding(
        audit_id=audit_id, business_id=business["business_id"], category="on_page",
        rule_code="missing_title", severity="high", issue="Missing title", affected_url="https://greenleaf.test/",
    ))
    db_session.commit()

    resp = client.get(f"/api/agents/seo/audits/{audit_id}/report", headers=business["headers"])

    assert resp.status_code == 200
    body = resp.json()
    assert body["website_url"] == "https://greenleaf.test"
    assert body["overall_health"] == 80
    assert body["executive_summary"] == "Fix missing titles first."
    assert body["finding_counts"]["high"] == 1
    assert len(body["top_action_items"]) == 1
    assert body["top_action_items"][0]["rule_code"] == "missing_title"
    assert body["keyword_opportunity_count"] == 0


def test_cannot_get_another_businesss_report(client, business, signup, grant_agent, monkeypatch):
    _entitle(business, grant_agent)
    other = signup()
    grant_agent(other["business_id"], "seo_audit_optimization")
    _stub_public_url(monkeypatch)

    create_resp = client.post("/api/agents/seo/websites", json={"url": "https://theirs.test"}, headers=other["headers"])
    website_id = create_resp.json()["id"]
    audit_resp = client.post(f"/api/agents/seo/websites/{website_id}/audits", headers=other["headers"])
    audit_id = audit_resp.json()["id"]

    resp = client.get(f"/api/agents/seo/audits/{audit_id}/report", headers=business["headers"])
    assert resp.status_code == 404
