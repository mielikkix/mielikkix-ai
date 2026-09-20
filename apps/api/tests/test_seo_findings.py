"""Integration tests for Stage 3 (apps/agents/seo-audit/CLAUDE.md):
run_audit's technical-analyzer pass actually producing SeoFinding rows and
a health_technical score, plus the findings list/update HTTP surface.
Pure rule-logic is covered by test_seo_technical_analyzer.py; this file
covers the wiring.
"""
from unittest.mock import AsyncMock

import pytest

from app.models.seo_audit import SeoAudit, SeoFinding
from app.models.seo_website import SeoWebsite
from app.services import seo_audit_service, seo_page_analyzer, web_crawl


def _entitle(business, grant_agent):
    grant_agent(business["business_id"], "seo_audit_optimization")


def _stub_public_url(monkeypatch):
    from app.services import seo_website_service
    monkeypatch.setattr(seo_website_service.web_crawl, "assert_public_url", lambda url: None)


def _make_website(client, headers) -> str:
    resp = client.post("/api/agents/seo/websites", json={"url": "https://greenleaf.test"}, headers=headers)
    assert resp.status_code == 200, resp.text
    return resp.json()["id"]


def _fake_analysis(url: str, **overrides) -> seo_page_analyzer.PageAnalysis:
    defaults = dict(
        url=url, http_status=200, title="A title", meta_description="A description",
        h1_count=1, word_count=120, canonical_url=url, meta_robots=None, x_robots_tag=None,
        is_indexable=True, redirect_chain=[url], internal_link_count=3, image_count=2, images_missing_alt=1,
    )
    defaults.update(overrides)
    return seo_page_analyzer.PageAnalysis(**defaults)


@pytest.fixture()
def use_test_db_for_audit(monkeypatch, db_session):
    monkeypatch.setattr(seo_audit_service, "SessionLocal", lambda: db_session)


@pytest.mark.asyncio
async def test_run_audit_produces_findings_and_a_health_score(business, db_session, monkeypatch, use_test_db_for_audit):
    website = SeoWebsite(business_id=business["business_id"], url="https://greenleaf.test", crawl_tier="starter")
    db_session.add(website)
    db_session.commit()
    audit = seo_audit_service.create_audit(db_session, website)
    audit_id = audit.id
    website_business_id = website.business_id

    monkeypatch.setattr(web_crawl, "discover_website_pages", AsyncMock(return_value=["https://greenleaf.test/broken"]))
    monkeypatch.setattr(
        seo_page_analyzer, "analyze_page",
        AsyncMock(return_value=_fake_analysis("https://greenleaf.test/broken", http_status=404)),
    )
    # No robots.txt, no sitemap -- both fetched fresh by the technical pass.
    monkeypatch.setattr(web_crawl, "fetch_robots_txt_text", AsyncMock(return_value=None))
    monkeypatch.setattr(web_crawl, "discover_sitemap_urls", AsyncMock(return_value=[]))

    await seo_audit_service.run_audit(str(audit_id))

    audit = db_session.query(SeoAudit).filter(SeoAudit.id == audit_id).first()
    assert audit.status == "completed"
    assert audit.health_technical is not None
    assert audit.health_technical < 100  # a 404 page + missing robots/sitemap all deduct

    findings = db_session.query(SeoFinding).filter(SeoFinding.audit_id == audit_id).all()
    codes = {f.rule_code for f in findings}
    assert "broken_page" in codes
    assert "robots_missing" in codes
    assert "sitemap_missing" in codes
    assert all(f.business_id == website_business_id for f in findings)


@pytest.mark.asyncio
async def test_run_audit_with_no_technical_issues_has_a_perfect_score(business, db_session, monkeypatch, use_test_db_for_audit):
    website = SeoWebsite(business_id=business["business_id"], url="https://greenleaf.test", crawl_tier="starter")
    db_session.add(website)
    db_session.commit()
    audit = seo_audit_service.create_audit(db_session, website)
    audit_id = audit.id

    monkeypatch.setattr(web_crawl, "discover_website_pages", AsyncMock(return_value=["https://greenleaf.test/"]))
    monkeypatch.setattr(seo_page_analyzer, "analyze_page", AsyncMock(return_value=_fake_analysis("https://greenleaf.test/")))
    monkeypatch.setattr(
        web_crawl, "fetch_robots_txt_text",
        AsyncMock(return_value="User-agent: *\nSitemap: https://greenleaf.test/sitemap.xml\n"),
    )
    monkeypatch.setattr(web_crawl, "discover_sitemap_urls", AsyncMock(return_value=["https://greenleaf.test/"]))

    await seo_audit_service.run_audit(str(audit_id))

    audit = db_session.query(SeoAudit).filter(SeoAudit.id == audit_id).first()
    assert audit.health_technical == 100


def test_list_findings_requires_entitlement(client, business):
    resp = client.get(
        "/api/agents/seo/audits/00000000-0000-0000-0000-000000000000/findings", headers=business["headers"]
    )
    assert resp.status_code == 403


def test_list_findings_filters_by_severity(client, business, grant_agent, monkeypatch, db_session):
    _entitle(business, grant_agent)
    _stub_public_url(monkeypatch)
    website_id = _make_website(client, business["headers"])
    create_resp = client.post(f"/api/agents/seo/websites/{website_id}/audits", headers=business["headers"])
    audit_id = create_resp.json()["id"]

    db_session.add(SeoFinding(
        audit_id=audit_id, business_id=business["business_id"], category="technical",
        rule_code="broken_page", severity="high", issue="404", affected_url="https://x/gone",
    ))
    db_session.add(SeoFinding(
        audit_id=audit_id, business_id=business["business_id"], category="technical",
        rule_code="missing_canonical", severity="low", issue="no canonical",
    ))
    db_session.commit()

    resp = client.get(f"/api/agents/seo/audits/{audit_id}/findings", params={"severity": "high"}, headers=business["headers"])
    assert resp.status_code == 200
    body = resp.json()
    assert len(body) == 1
    assert body[0]["rule_code"] == "broken_page"


def test_findings_sorted_most_severe_first(client, business, grant_agent, monkeypatch, db_session):
    _entitle(business, grant_agent)
    _stub_public_url(monkeypatch)
    website_id = _make_website(client, business["headers"])
    create_resp = client.post(f"/api/agents/seo/websites/{website_id}/audits", headers=business["headers"])
    audit_id = create_resp.json()["id"]

    for severity in ["low", "critical", "medium"]:
        db_session.add(SeoFinding(
            audit_id=audit_id, business_id=business["business_id"], category="technical",
            rule_code=f"rule_{severity}", severity=severity, issue="x",
        ))
    db_session.commit()

    resp = client.get(f"/api/agents/seo/audits/{audit_id}/findings", headers=business["headers"])
    severities = [f["severity"] for f in resp.json()]
    assert severities == ["critical", "medium", "low"]


def test_cannot_list_another_businesss_findings(client, business, signup, grant_agent, monkeypatch, db_session):
    _entitle(business, grant_agent)
    other = signup()
    grant_agent(other["business_id"], "seo_audit_optimization")
    _stub_public_url(monkeypatch)

    other_website_id = _make_website(client, other["headers"])
    create_resp = client.post(f"/api/agents/seo/websites/{other_website_id}/audits", headers=other["headers"])
    audit_id = create_resp.json()["id"]

    resp = client.get(f"/api/agents/seo/audits/{audit_id}/findings", headers=business["headers"])
    assert resp.status_code == 404


def test_update_finding_status(client, business, grant_agent, monkeypatch, db_session):
    _entitle(business, grant_agent)
    _stub_public_url(monkeypatch)
    website_id = _make_website(client, business["headers"])
    create_resp = client.post(f"/api/agents/seo/websites/{website_id}/audits", headers=business["headers"])
    audit_id = create_resp.json()["id"]

    finding = SeoFinding(
        audit_id=audit_id, business_id=business["business_id"], category="technical",
        rule_code="missing_canonical", severity="low", issue="no canonical",
    )
    db_session.add(finding)
    db_session.commit()

    resp = client.patch(f"/api/agents/seo/findings/{finding.id}", json={"status": "ignored"}, headers=business["headers"])
    assert resp.status_code == 200
    assert resp.json()["status"] == "ignored"


def test_update_finding_status_rejects_unknown_status(client, business, grant_agent, monkeypatch, db_session):
    _entitle(business, grant_agent)
    _stub_public_url(monkeypatch)
    website_id = _make_website(client, business["headers"])
    create_resp = client.post(f"/api/agents/seo/websites/{website_id}/audits", headers=business["headers"])
    audit_id = create_resp.json()["id"]

    finding = SeoFinding(
        audit_id=audit_id, business_id=business["business_id"], category="technical",
        rule_code="missing_canonical", severity="low", issue="no canonical",
    )
    db_session.add(finding)
    db_session.commit()

    resp = client.patch(f"/api/agents/seo/findings/{finding.id}", json={"status": "bogus"}, headers=business["headers"])
    assert resp.status_code == 400


def test_cannot_update_another_businesss_finding(client, business, signup, grant_agent, monkeypatch, db_session):
    _entitle(business, grant_agent)
    other = signup()
    grant_agent(other["business_id"], "seo_audit_optimization")
    _stub_public_url(monkeypatch)

    other_website_id = _make_website(client, other["headers"])
    create_resp = client.post(f"/api/agents/seo/websites/{other_website_id}/audits", headers=other["headers"])
    audit_id = create_resp.json()["id"]

    finding = SeoFinding(
        audit_id=audit_id, business_id=other["business_id"], category="technical",
        rule_code="missing_canonical", severity="low", issue="no canonical",
    )
    db_session.add(finding)
    db_session.commit()

    resp = client.patch(f"/api/agents/seo/findings/{finding.id}", json={"status": "ignored"}, headers=business["headers"])
    assert resp.status_code == 404
