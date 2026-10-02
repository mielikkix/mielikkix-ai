"""Claude/OpenAI usage logging for the admin AI Usage page (core/llm_usage.py):
agent-core LLMClient calls -> llm_usage_logs, attributed to the logged-in
business, or to none for the public demos."""

import json
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient

from app.core import llm_usage
from app.core.config import settings
from app.core.database import get_db
from app.core.dependencies import get_current_user
from app.models.llm_usage import LLMUsageLog
from app.services import support_service
from mielikkix_agent_core import LLMClient


def _fake_anthropic(client: LLMClient, text: str, prompt=20, completion=5):
    response = SimpleNamespace(
        content=[SimpleNamespace(type="text", text=text)],
        usage=SimpleNamespace(input_tokens=prompt, output_tokens=completion),
    )
    client._get_client = lambda: SimpleNamespace(messages=SimpleNamespace(create=AsyncMock(return_value=response)))


def test_public_demo_call_is_logged_with_provider_feature_and_no_business(client, db_session, monkeypatch):
    monkeypatch.setattr(support_service, "_retrieve_context", lambda db, query: "")
    llm = LLMClient(provider="anthropic", api_key="k", model="claude-test", usage_tag="support_triage")
    _fake_anthropic(llm, json.dumps({"category": "general", "priority": "low", "confidence": 0.9, "answer": "Hi"}))
    monkeypatch.setattr(support_service, "_llm_client", llm)

    resp = client.post("/api/agents/support/chat/message", json={"session_id": "u1", "message": "hello"})

    assert resp.status_code == 200
    rows = db_session.query(LLMUsageLog).all()
    assert [(r.provider, r.model, r.kind, r.business_id, r.total_tokens) for r in rows] == [
        ("anthropic", "claude-test", "support_triage", None, 25)
    ]


def test_logged_in_calls_are_attributed_to_the_business(db_session, business):
    """get_current_user is a sync dependency, so FastAPI runs it in a worker
    thread with a COPY of the request context -- this checks the business it
    records still reaches the async route (and so the LLM call)."""
    app = FastAPI()
    app.add_middleware(llm_usage.UsageContextMiddleware)

    @app.get("/probe")
    async def probe(user=Depends(get_current_user)):
        llm = LLMClient(provider="anthropic", api_key="k", model="m", usage_tag="reviews")
        _fake_anthropic(llm, "ok")
        await llm.chat([{"role": "user", "content": "hi"}])
        return {"ok": True}

    app.dependency_overrides[get_db] = lambda: db_session
    resp = TestClient(app).get("/probe", headers=business["headers"])

    assert resp.status_code == 200
    row = db_session.query(LLMUsageLog).one()
    assert str(row.business_id) == business["business_id"]
    assert row.kind == "reviews"


@pytest.mark.asyncio
async def test_scheduled_work_can_attribute_usage_explicitly(db_session, business):
    llm = LLMClient(provider="openai", api_key="k", model="gpt-mini", usage_tag="seo_recommendations")
    response = SimpleNamespace(
        choices=[SimpleNamespace(message=SimpleNamespace(content="x", tool_calls=None))],
        usage=SimpleNamespace(prompt_tokens=7, completion_tokens=3, total_tokens=10),
    )
    llm._get_client = lambda: SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=AsyncMock(return_value=response))))

    with llm_usage.usage_business(business["business_id"]):
        await llm.chat([{"role": "user", "content": "hi"}])

    row = db_session.query(LLMUsageLog).one()
    assert (row.provider, str(row.business_id), row.total_tokens) == ("openai", business["business_id"], 10)


def test_admin_usage_shows_every_provider_with_breakdowns_and_filter(client, business, db_session, monkeypatch):
    monkeypatch.setattr(settings, "platform_admin_emails", business["email"])
    db_session.add_all([
        LLMUsageLog(business_id=business["business_id"], provider="groq", kind="chat", prompt_tokens=80, completion_tokens=20, total_tokens=100),
        LLMUsageLog(business_id=None, provider="anthropic", kind="support_triage", prompt_tokens=40, completion_tokens=10, total_tokens=50),
        LLMUsageLog(business_id=business["business_id"], provider="openai", kind="seo_copywriter", prompt_tokens=20, completion_tokens=5, total_tokens=25),
    ])
    db_session.commit()

    body = client.get("/api/admin/llm-usage", headers=business["headers"]).json()
    assert body["totals"]["total_tokens"] == 175
    assert [p["key"] for p in body["by_provider"]] == ["groq", "anthropic", "openai"]
    assert {f["key"] for f in body["by_feature"]} == {"chat", "support_triage", "seo_copywriter"}
    demos = [b for b in body["by_business"] if b["business_id"] is None]
    assert demos == [{"business_id": None, "business_name": "Platform / public demos", "requests": 1, "total_tokens": 50}]

    only_claude = client.get("/api/admin/llm-usage", params={"provider": "anthropic"}, headers=business["headers"]).json()
    assert only_claude["totals"]["total_tokens"] == 50
    assert client.get("/api/admin/llm-usage", params={"provider": "nope"}, headers=business["headers"]).status_code == 422
