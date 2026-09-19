"""Tests for Stage 7 (apps/agents/seo-copywriter/CLAUDE.md): generating a
Copywriter draft FROM an SEO Audit finding, instead of from the product
picker. The LLM client is always mocked here -- no test makes a real call.
"""
import json
from unittest.mock import AsyncMock

import pytest

from app.models.seo_audit import SeoAudit, SeoCrawledPage, SeoFinding
from app.models.seo_draft import SeoDraft
from app.models.seo_website import SeoWebsite
from app.services import seo_service
from mielikkix_agent_core import LLMResult


def _fake_llm_response(json_text: str) -> LLMResult:
    return LLMResult(text=json_text, usage=None)


def _entitle(business, grant_agent):
    grant_agent(business["business_id"], "seo_audit_optimization")


def _make_website_audit_finding(db_session, business_id, rule_code="missing_title", affected_url="https://greenleaf.test/"):
    website = SeoWebsite(business_id=business_id, url="https://greenleaf.test", crawl_tier="starter")
    db_session.add(website)
    db_session.commit()

    audit = SeoAudit(website_id=website.id, business_id=business_id, status="completed")
    db_session.add(audit)
    db_session.commit()

    page = SeoCrawledPage(
        audit_id=audit.id, url=affected_url, http_status=200, title="Old Title",
        meta_description="Old meta description here.", word_count=50,
    )
    db_session.add(page)

    finding = SeoFinding(
        audit_id=audit.id, business_id=business_id, category="on_page",
        rule_code=rule_code, severity="high", issue="Something is wrong", affected_url=affected_url,
    )
    db_session.add(finding)
    db_session.commit()
    return website, audit, finding


# ---------------------------------------------------------------------------
# Service layer -- generate_draft_for_finding
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_generates_a_title_draft_for_a_title_finding(business, db_session, monkeypatch):
    _, _, finding = _make_website_audit_finding(db_session, business["business_id"], rule_code="missing_title")
    monkeypatch.setattr(
        seo_service._llm_client, "chat",
        AsyncMock(return_value=_fake_llm_response(json.dumps({"seo_title": "Organic Coffee in Oslo | Green Leaf"}))),
    )

    draft = await seo_service.generate_draft_for_finding(db_session, str(business["business_id"]), str(finding.id))

    assert draft.draft_type == "title"
    assert draft.draft_seo_title == "Organic Coffee in Oslo | Green Leaf"
    assert draft.draft_meta_description is None
    assert draft.draft_description is None
    assert draft.product_id is None
    assert draft.url == "https://greenleaf.test/"
    assert draft.status == "draft"


@pytest.mark.asyncio
async def test_generates_a_meta_description_draft(business, db_session, monkeypatch):
    _, _, finding = _make_website_audit_finding(db_session, business["business_id"], rule_code="missing_meta_description")
    monkeypatch.setattr(
        seo_service._llm_client, "chat",
        AsyncMock(return_value=_fake_llm_response(json.dumps({"meta_description": "Fresh organic coffee, roasted daily in Oslo."}))),
    )

    draft = await seo_service.generate_draft_for_finding(db_session, str(business["business_id"]), str(finding.id))

    assert draft.draft_type == "meta_description"
    assert draft.draft_meta_description == "Fresh organic coffee, roasted daily in Oslo."
    assert draft.draft_seo_title is None


@pytest.mark.asyncio
async def test_generates_a_content_suggestion_for_thin_content(business, db_session, monkeypatch):
    _, _, finding = _make_website_audit_finding(db_session, business["business_id"], rule_code="thin_content")
    monkeypatch.setattr(
        seo_service._llm_client, "chat",
        AsyncMock(return_value=_fake_llm_response(json.dumps({"content_suggestion": "Cover your roasting process and sourcing."}))),
    )

    draft = await seo_service.generate_draft_for_finding(db_session, str(business["business_id"]), str(finding.id))

    assert draft.draft_type == "content"
    assert draft.draft_description == "Cover your roasting process and sourcing."


@pytest.mark.asyncio
async def test_unsupported_rule_code_raises(business, db_session):
    _, _, finding = _make_website_audit_finding(db_session, business["business_id"], rule_code="images_missing_alt")

    with pytest.raises(seo_service.UnsupportedFindingError):
        await seo_service.generate_draft_for_finding(db_session, str(business["business_id"]), str(finding.id))


@pytest.mark.asyncio
async def test_unknown_finding_raises_value_error(business, db_session):
    with pytest.raises(ValueError):
        await seo_service.generate_draft_for_finding(
            db_session, str(business["business_id"]), "00000000-0000-0000-0000-000000000000"
        )


@pytest.mark.asyncio
async def test_malformed_llm_json_raises_draft_generation_error(business, db_session, monkeypatch):
    _, _, finding = _make_website_audit_finding(db_session, business["business_id"], rule_code="missing_title")
    monkeypatch.setattr(seo_service._llm_client, "chat", AsyncMock(return_value=_fake_llm_response("not json")))

    with pytest.raises(seo_service.DraftGenerationError):
        await seo_service.generate_draft_for_finding(db_session, str(business["business_id"]), str(finding.id))


@pytest.mark.asyncio
async def test_llm_failure_raises_draft_generation_error(business, db_session, monkeypatch):
    _, _, finding = _make_website_audit_finding(db_session, business["business_id"], rule_code="missing_title")
    monkeypatch.setattr(seo_service._llm_client, "chat", AsyncMock(side_effect=RuntimeError("provider down")))

    with pytest.raises(seo_service.DraftGenerationError):
        await seo_service.generate_draft_for_finding(db_session, str(business["business_id"]), str(finding.id))


@pytest.mark.asyncio
async def test_cannot_generate_a_draft_for_another_businesss_finding(business, signup, db_session, monkeypatch):
    other = signup()
    _, _, finding = _make_website_audit_finding(db_session, other["business_id"], rule_code="missing_title")

    with pytest.raises(ValueError):
        await seo_service.generate_draft_for_finding(db_session, str(business["business_id"]), str(finding.id))


# ---------------------------------------------------------------------------
# HTTP surface
# ---------------------------------------------------------------------------

def test_generate_finding_draft_requires_entitlement(client, business):
    resp = client.post(
        "/api/agents/seo/findings/00000000-0000-0000-0000-000000000000/generate-draft",
        headers=business["headers"],
    )
    assert resp.status_code == 403


def test_generate_finding_draft_success(client, business, grant_agent, db_session, monkeypatch):
    _entitle(business, grant_agent)
    _, _, finding = _make_website_audit_finding(db_session, business["business_id"], rule_code="missing_title")
    monkeypatch.setattr(
        seo_service._llm_client, "chat",
        AsyncMock(return_value=_fake_llm_response(json.dumps({"seo_title": "A Great New Title"}))),
    )

    resp = client.post(f"/api/agents/seo/findings/{finding.id}/generate-draft", headers=business["headers"])

    assert resp.status_code == 200
    body = resp.json()
    assert body["draft_type"] == "title"
    assert body["draft_seo_title"] == "A Great New Title"
    assert body["product_id"] is None
    assert body["finding_id"] == str(finding.id)
    assert body["status"] == "draft"


def test_generate_finding_draft_unsupported_rule_code_400s(client, business, grant_agent, db_session):
    _entitle(business, grant_agent)
    _, _, finding = _make_website_audit_finding(db_session, business["business_id"], rule_code="duplicate_content")

    resp = client.post(f"/api/agents/seo/findings/{finding.id}/generate-draft", headers=business["headers"])
    assert resp.status_code == 400


def test_generate_finding_draft_llm_failure_maps_to_502(client, business, grant_agent, db_session, monkeypatch):
    _entitle(business, grant_agent)
    _, _, finding = _make_website_audit_finding(db_session, business["business_id"], rule_code="missing_title")
    monkeypatch.setattr(seo_service._llm_client, "chat", AsyncMock(side_effect=RuntimeError("down")))

    resp = client.post(f"/api/agents/seo/findings/{finding.id}/generate-draft", headers=business["headers"])
    assert resp.status_code == 502


def test_generate_finding_draft_unknown_finding_404s(client, business, grant_agent):
    _entitle(business, grant_agent)
    resp = client.post(
        "/api/agents/seo/findings/00000000-0000-0000-0000-000000000000/generate-draft", headers=business["headers"]
    )
    assert resp.status_code == 404


def test_cannot_generate_draft_for_another_businesss_finding(client, business, signup, grant_agent, db_session):
    _entitle(business, grant_agent)
    other = signup()
    _, _, finding = _make_website_audit_finding(db_session, other["business_id"], rule_code="missing_title")

    resp = client.post(f"/api/agents/seo/findings/{finding.id}/generate-draft", headers=business["headers"])
    assert resp.status_code == 404


def test_list_finding_drafts(client, business, grant_agent, db_session, monkeypatch):
    _entitle(business, grant_agent)
    _, _, finding = _make_website_audit_finding(db_session, business["business_id"], rule_code="missing_title")
    monkeypatch.setattr(
        seo_service._llm_client, "chat",
        AsyncMock(return_value=_fake_llm_response(json.dumps({"seo_title": "Title One"}))),
    )
    client.post(f"/api/agents/seo/findings/{finding.id}/generate-draft", headers=business["headers"])

    resp = client.get(f"/api/agents/seo/findings/{finding.id}/drafts", headers=business["headers"])

    assert resp.status_code == 200
    assert len(resp.json()) == 1
    assert resp.json()[0]["draft_seo_title"] == "Title One"


def test_approve_a_finding_driven_draft_does_not_crash_with_no_product(client, business, grant_agent, db_session, monkeypatch):
    """No Product row exists for a crawled page -- approving must not try
    to write to one, and should just mark the draft approved (see
    seo_service.approve_draft's own docstring)."""
    _entitle(business, grant_agent)
    _, _, finding = _make_website_audit_finding(db_session, business["business_id"], rule_code="missing_title")
    monkeypatch.setattr(
        seo_service._llm_client, "chat",
        AsyncMock(return_value=_fake_llm_response(json.dumps({"seo_title": "A Title"}))),
    )
    gen_resp = client.post(f"/api/agents/seo/findings/{finding.id}/generate-draft", headers=business["headers"])
    draft_id = gen_resp.json()["id"]

    resp = client.post(f"/api/agents/seo/drafts/{draft_id}/approve", headers=business["headers"])

    assert resp.status_code == 200
    assert resp.json()["status"] == "approved"


def test_reject_a_finding_driven_draft(client, business, grant_agent, db_session, monkeypatch):
    _entitle(business, grant_agent)
    _, _, finding = _make_website_audit_finding(db_session, business["business_id"], rule_code="missing_title")
    monkeypatch.setattr(
        seo_service._llm_client, "chat",
        AsyncMock(return_value=_fake_llm_response(json.dumps({"seo_title": "A Title"}))),
    )
    gen_resp = client.post(f"/api/agents/seo/findings/{finding.id}/generate-draft", headers=business["headers"])
    draft_id = gen_resp.json()["id"]

    resp = client.post(f"/api/agents/seo/drafts/{draft_id}/reject", headers=business["headers"])

    assert resp.status_code == 200
    assert resp.json()["status"] == "rejected"
