"""SEO Copywriter tests (see apps/agents/seo-copywriter/CLAUDE.md). The LLM
client is always mocked here -- no test makes a real Groq call."""

import json
from unittest.mock import AsyncMock

import pytest

from app.models.product import Product
from app.models.seo_draft import SeoDraft
from app.services import seo_service
from mielikkix_agent_core import LLMResult


def _fake_llm_response(json_text: str) -> LLMResult:
    return LLMResult(text=json_text, usage=None)


def _mock_generation(monkeypatch, description="A rewritten description.", seo_title="Great Widget | Buy Now", meta_description="The best widget for your needs, shipped fast."):
    fake_chat = AsyncMock(
        return_value=_fake_llm_response(
            json.dumps(
                {"description": description, "seo_title": seo_title, "meta_description": meta_description}
            )
        )
    )
    monkeypatch.setattr(seo_service._llm_client, "chat", fake_chat)
    return fake_chat


def _make_product(client, headers, **overrides) -> str:
    body = {"name": "Widget", "description": "A basic widget.", "category": "gadgets"}
    body.update(overrides)
    resp = client.post("/api/products", json=body, headers=headers)
    assert resp.status_code == 200, resp.text
    return resp.json()["id"]


def test_generate_requires_seo_copywriter_entitlement(client, business):
    resp = client.post(
        "/api/agents/seo/drafts/generate", json={"product_ids": []}, headers=business["headers"]
    )
    assert resp.status_code == 403


def test_generate_creates_a_draft_for_an_owned_product(client, business, set_plan, monkeypatch):
    set_plan(business["business_id"], "business")
    product_id = _make_product(client, business["headers"])
    _mock_generation(monkeypatch)

    resp = client.post(
        "/api/agents/seo/drafts/generate",
        json={"product_ids": [product_id]},
        headers=business["headers"],
    )

    assert resp.status_code == 200
    body = resp.json()
    assert len(body) == 1
    assert body[0]["product_id"] == product_id
    assert body[0]["status"] == "draft"
    assert body[0]["draft_description"] == "A rewritten description."


def test_generate_skips_a_product_belonging_to_another_business(client, business, signup, set_plan, monkeypatch):
    set_plan(business["business_id"], "business")
    other = signup()
    set_plan(other["business_id"], "business")
    other_product_id = _make_product(client, other["headers"])
    _mock_generation(monkeypatch)

    resp = client.post(
        "/api/agents/seo/drafts/generate",
        json={"product_ids": [other_product_id]},
        headers=business["headers"],
    )

    assert resp.status_code == 200
    assert resp.json() == []


def test_generate_skips_a_product_on_malformed_llm_json(client, business, set_plan, monkeypatch):
    set_plan(business["business_id"], "business")
    product_id = _make_product(client, business["headers"])
    monkeypatch.setattr(seo_service._llm_client, "chat", AsyncMock(return_value=_fake_llm_response("not json")))

    resp = client.post(
        "/api/agents/seo/drafts/generate",
        json={"product_ids": [product_id]},
        headers=business["headers"],
    )

    assert resp.status_code == 200
    assert resp.json() == []


def test_generate_skips_a_product_when_the_llm_call_itself_fails(client, business, set_plan, monkeypatch):
    """Regression: confirmed live on 2026-08-28 -- a real Groq rate-limit
    error (RateLimitError, not a malformed-response problem) propagated
    uncaught out of _generate_one and 500'd the whole /drafts/generate
    request instead of just skipping that one product."""
    set_plan(business["business_id"], "business")
    product_id = _make_product(client, business["headers"])
    monkeypatch.setattr(seo_service._llm_client, "chat", AsyncMock(side_effect=RuntimeError("groq is down")))

    resp = client.post(
        "/api/agents/seo/drafts/generate",
        json={"product_ids": [product_id]},
        headers=business["headers"],
    )

    assert resp.status_code == 200
    assert resp.json() == []


def test_list_drafts_filters_by_status(client, business, set_plan, monkeypatch):
    set_plan(business["business_id"], "business")
    product_id = _make_product(client, business["headers"])
    _mock_generation(monkeypatch)
    client.post("/api/agents/seo/drafts/generate", json={"product_ids": [product_id]}, headers=business["headers"])

    resp = client.get("/api/agents/seo/drafts", params={"status": "draft"}, headers=business["headers"])
    assert len(resp.json()) == 1

    resp = client.get("/api/agents/seo/drafts", params={"status": "approved"}, headers=business["headers"])
    assert resp.json() == []


def test_approve_draft_copies_onto_the_real_product_and_reembeds(client, business, set_plan, monkeypatch, db_session):
    set_plan(business["business_id"], "business")
    product_id = _make_product(client, business["headers"], description="Old description.")
    _mock_generation(monkeypatch, description="New, better description.", seo_title="New Title", meta_description="New meta.")
    gen_resp = client.post(
        "/api/agents/seo/drafts/generate", json={"product_ids": [product_id]}, headers=business["headers"]
    )
    draft_id = gen_resp.json()[0]["id"]

    monkeypatch.setattr(seo_service, "embed_query", lambda text: [0.1, 0.2])

    resp = client.post(f"/api/agents/seo/drafts/{draft_id}/approve", headers=business["headers"])

    assert resp.status_code == 200
    assert resp.json()["status"] == "approved"

    product = db_session.query(Product).filter(Product.id == product_id).first()
    assert product.description == "New, better description."
    assert product.seo_title == "New Title"
    assert product.meta_description == "New meta."
    assert product.embedding_json == json.dumps([0.1, 0.2])


def test_reject_draft_does_not_touch_the_live_product(client, business, set_plan, monkeypatch, db_session):
    set_plan(business["business_id"], "business")
    product_id = _make_product(client, business["headers"], description="Untouched description.")
    _mock_generation(monkeypatch, description="Would-be new description.")
    gen_resp = client.post(
        "/api/agents/seo/drafts/generate", json={"product_ids": [product_id]}, headers=business["headers"]
    )
    draft_id = gen_resp.json()[0]["id"]

    resp = client.post(f"/api/agents/seo/drafts/{draft_id}/reject", headers=business["headers"])

    assert resp.status_code == 200
    assert resp.json()["status"] == "rejected"

    product = db_session.query(Product).filter(Product.id == product_id).first()
    assert product.description == "Untouched description."


def test_approve_unknown_draft_404s(client, business, set_plan):
    set_plan(business["business_id"], "business")
    resp = client.post(
        "/api/agents/seo/drafts/00000000-0000-0000-0000-000000000000/approve", headers=business["headers"]
    )
    assert resp.status_code == 404


def test_cannot_approve_another_businesss_draft(client, business, signup, set_plan, monkeypatch, db_session):
    set_plan(business["business_id"], "business")
    other = signup()
    set_plan(other["business_id"], "business")
    other_product_id = _make_product(client, other["headers"])
    _mock_generation(monkeypatch)
    gen_resp = client.post(
        "/api/agents/seo/drafts/generate", json={"product_ids": [other_product_id]}, headers=other["headers"]
    )
    draft_id = gen_resp.json()[0]["id"]

    resp = client.post(f"/api/agents/seo/drafts/{draft_id}/approve", headers=business["headers"])

    assert resp.status_code == 404


# --- Public demo endpoint (website/'s /demo/seo-copywriter page) ---


def test_demo_endpoint_requires_no_auth(client, monkeypatch):
    _mock_generation(monkeypatch, description="A great, specific description.", seo_title="Great Widget | Shop Now")

    resp = client.post("/api/agents/seo/demo", json={"name": "Widget", "category": "gadgets"})

    assert resp.status_code == 200
    body = resp.json()
    assert body["description"] == "A great, specific description."
    assert body["seo_title"] == "Great Widget | Shop Now"


def test_demo_endpoint_never_creates_a_product_or_draft(client, db_session, monkeypatch):
    _mock_generation(monkeypatch)
    before_products = db_session.query(Product).count()
    before_drafts = db_session.query(SeoDraft).count()

    client.post("/api/agents/seo/demo", json={"name": "Widget"})

    assert db_session.query(Product).count() == before_products
    assert db_session.query(SeoDraft).count() == before_drafts


def test_demo_endpoint_works_with_only_a_name(client, monkeypatch):
    fake_chat = _mock_generation(monkeypatch)

    resp = client.post("/api/agents/seo/demo", json={"name": "Widget"})

    assert resp.status_code == 200
    sent_prompt = fake_chat.call_args.args[0][1]["content"]
    assert "Widget" in sent_prompt
    assert "(none given)" in sent_prompt
