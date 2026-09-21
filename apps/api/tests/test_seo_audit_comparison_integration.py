"""Integration tests for Stage 10 (apps/agents/seo-audit/CLAUDE.md):
the GET .../audits/{id}/compare HTTP endpoint. Pure diff/matching logic is
covered by test_seo_audit_comparison_service.py; this file covers
entitlement, 404s, and cross-business isolation.
"""
from app.models.seo_audit import SeoFinding
from app.models.seo_website import SeoWebsite


def _entitle(business, grant_agent):
    grant_agent(business["business_id"], "seo_audit_optimization")


def _stub_public_url(monkeypatch):
    from app.services import seo_website_service
    monkeypatch.setattr(seo_website_service.web_crawl, "assert_public_url", lambda url: None)


def _create_audit(client, business, url="https://greenleaf.test"):
    create_resp = client.post("/api/agents/seo/websites", json={"url": url}, headers=business["headers"])
    website_id = create_resp.json()["id"]
    audit_resp = client.post(f"/api/agents/seo/websites/{website_id}/audits", headers=business["headers"])
    return audit_resp.json()["id"]


def test_compare_requires_entitlement(client, business):
    resp = client.get(
        "/api/agents/seo/audits/00000000-0000-0000-0000-000000000000/compare"
        "?against=00000000-0000-0000-0000-000000000001",
        headers=business["headers"],
    )
    assert resp.status_code == 403


def test_compare_404s_when_either_audit_is_unknown(client, business, grant_agent, monkeypatch):
    _entitle(business, grant_agent)
    _stub_public_url(monkeypatch)
    audit_id = _create_audit(client, business)

    resp = client.get(
        f"/api/agents/seo/audits/{audit_id}/compare?against=00000000-0000-0000-0000-000000000000",
        headers=business["headers"],
    )
    assert resp.status_code == 404


def test_compare_400s_for_audits_of_different_websites(client, business, grant_agent, monkeypatch):
    _entitle(business, grant_agent)
    _stub_public_url(monkeypatch)
    audit_a = _create_audit(client, business, url="https://a.test")
    audit_b = _create_audit(client, business, url="https://b.test")

    resp = client.get(f"/api/agents/seo/audits/{audit_a}/compare?against={audit_b}", headers=business["headers"])
    assert resp.status_code == 400


def test_compare_diffs_findings_and_health_between_two_real_audits(client, business, grant_agent, monkeypatch, db_session):
    _entitle(business, grant_agent)
    _stub_public_url(monkeypatch)
    create_resp = client.post("/api/agents/seo/websites", json={"url": "https://greenleaf.test"}, headers=business["headers"])
    website_id = create_resp.json()["id"]

    previous_resp = client.post(f"/api/agents/seo/websites/{website_id}/audits", headers=business["headers"])
    previous_id = previous_resp.json()["id"]
    db_session.add(SeoFinding(
        audit_id=previous_id, business_id=business["business_id"], category="on_page",
        rule_code="missing_title", severity="high", issue="Missing title", affected_url="https://greenleaf.test/",
    ))
    db_session.add(SeoFinding(
        audit_id=previous_id, business_id=business["business_id"], category="on_page",
        rule_code="missing_meta_description", severity="medium", issue="Missing meta",
        affected_url="https://greenleaf.test/",
    ))
    db_session.commit()

    current_resp = client.post(f"/api/agents/seo/websites/{website_id}/audits", headers=business["headers"])
    current_id = current_resp.json()["id"]
    # missing_title got fixed; missing_meta_description is still open;
    # thin_content is a newly detected issue this run.
    db_session.add(SeoFinding(
        audit_id=current_id, business_id=business["business_id"], category="on_page",
        rule_code="missing_meta_description", severity="medium", issue="Missing meta",
        affected_url="https://greenleaf.test/",
    ))
    db_session.add(SeoFinding(
        audit_id=current_id, business_id=business["business_id"], category="content",
        rule_code="thin_content", severity="medium", issue="Thin content", affected_url="https://greenleaf.test/",
    ))
    db_session.commit()

    resp = client.get(
        f"/api/agents/seo/audits/{current_id}/compare?against={previous_id}", headers=business["headers"]
    )

    assert resp.status_code == 200
    body = resp.json()
    assert body["previous_audit_id"] == previous_id
    assert body["current_audit_id"] == current_id
    assert [f["rule_code"] for f in body["resolved_findings"]] == ["missing_title"]
    assert [f["rule_code"] for f in body["new_findings"]] == ["thin_content"]
    assert [f["rule_code"] for f in body["persisting_findings"]] == ["missing_meta_description"]


def test_compare_result_is_identical_regardless_of_which_audit_id_is_in_the_path(
    client, business, grant_agent, monkeypatch, db_session
):
    _entitle(business, grant_agent)
    _stub_public_url(monkeypatch)
    create_resp = client.post("/api/agents/seo/websites", json={"url": "https://greenleaf.test"}, headers=business["headers"])
    website_id = create_resp.json()["id"]
    previous_id = client.post(f"/api/agents/seo/websites/{website_id}/audits", headers=business["headers"]).json()["id"]
    current_id = client.post(f"/api/agents/seo/websites/{website_id}/audits", headers=business["headers"]).json()["id"]

    forward = client.get(f"/api/agents/seo/audits/{current_id}/compare?against={previous_id}", headers=business["headers"])
    backward = client.get(f"/api/agents/seo/audits/{previous_id}/compare?against={current_id}", headers=business["headers"])

    assert forward.status_code == backward.status_code == 200
    assert forward.json()["previous_audit_id"] == backward.json()["previous_audit_id"] == previous_id
    assert forward.json()["current_audit_id"] == backward.json()["current_audit_id"] == current_id


def test_cannot_compare_another_businesss_audits(client, business, signup, grant_agent, monkeypatch):
    _entitle(business, grant_agent)
    other = signup()
    grant_agent(other["business_id"], "seo_audit_optimization")
    _stub_public_url(monkeypatch)

    other_audit_id = _create_audit(client, other, url="https://theirs.test")
    my_audit_id = _create_audit(client, business, url="https://mine.test")

    resp = client.get(
        f"/api/agents/seo/audits/{my_audit_id}/compare?against={other_audit_id}", headers=business["headers"]
    )
    assert resp.status_code == 404
