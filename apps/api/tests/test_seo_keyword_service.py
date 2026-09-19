"""Tests for Stage 9 (apps/agents/seo-copywriter/CLAUDE.md, Phase 14):
the keyword opportunity engine. The LLM client is always mocked here -- no
test makes a real call, and every test that matters here confirms
volume/CPC/competition are never fabricated.
"""
import json
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.services import seo_keyword_service as sks
from mielikkix_agent_core import LLMResult


def _fake_llm_response(json_text: str) -> LLMResult:
    return LLMResult(text=json_text, usage=None)


def _website(**overrides):
    defaults = dict(
        primary_category="Cafe", target_country="Norway", target_language="Norwegian",
        target_keywords=["organic coffee oslo"],
    )
    defaults.update(overrides)
    return SimpleNamespace(**defaults)


def _page(title="Green Leaf Cafe | Home", url="https://greenleaf.test/"):
    return SimpleNamespace(title=title, url=url)


VALID_RESPONSE = json.dumps({
    "keywords": [
        {
            "keyword": "organic coffee shop oslo",
            "intent": "commercial",
            "suggested_page": "https://greenleaf.test/",
            "current_page": "https://greenleaf.test/",
            "content_gap": None,
            "recommendation": "Add 'organic' to the homepage title.",
        },
        {
            "keyword": "best coffee roasters in oslo",
            "intent": "informational",
            "suggested_page": "A new blog post about the roasting process",
            "current_page": None,
            "content_gap": "No existing page discusses roasting.",
            "recommendation": "Write a blog post about your roasting process.",
        },
    ]
})


@pytest.mark.asyncio
async def test_generates_keyword_ideas_from_real_page_data(monkeypatch):
    monkeypatch.setattr(sks._llm_client, "chat", AsyncMock(return_value=_fake_llm_response(VALID_RESPONSE)))

    ideas = await sks.generate_keyword_ideas(_website(), [_page()])

    assert len(ideas) == 2
    assert ideas[0].keyword == "organic coffee shop oslo"
    assert ideas[0].intent == "commercial"
    assert ideas[1].content_gap == "No existing page discusses roasting."


@pytest.mark.asyncio
async def test_malformed_llm_json_raises_keyword_generation_error(monkeypatch):
    monkeypatch.setattr(sks._llm_client, "chat", AsyncMock(return_value=_fake_llm_response("not json")))

    with pytest.raises(sks.KeywordGenerationError):
        await sks.generate_keyword_ideas(_website(), [_page()])


@pytest.mark.asyncio
async def test_missing_keywords_list_raises(monkeypatch):
    monkeypatch.setattr(sks._llm_client, "chat", AsyncMock(return_value=_fake_llm_response(json.dumps({"foo": "bar"}))))

    with pytest.raises(sks.KeywordGenerationError):
        await sks.generate_keyword_ideas(_website(), [_page()])


@pytest.mark.asyncio
async def test_llm_call_failure_raises_keyword_generation_error(monkeypatch):
    monkeypatch.setattr(sks._llm_client, "chat", AsyncMock(side_effect=RuntimeError("provider down")))

    with pytest.raises(sks.KeywordGenerationError):
        await sks.generate_keyword_ideas(_website(), [_page()])


@pytest.mark.asyncio
async def test_malformed_individual_entry_is_skipped_not_fatal(monkeypatch):
    response = json.dumps({"keywords": [{"intent": "commercial"}, {"keyword": "a real keyword"}]})
    monkeypatch.setattr(sks._llm_client, "chat", AsyncMock(return_value=_fake_llm_response(response)))

    ideas = await sks.generate_keyword_ideas(_website(), [_page()])

    assert len(ideas) == 1
    assert ideas[0].keyword == "a real keyword"


@pytest.mark.asyncio
async def test_ideas_are_capped_at_max_keyword_ideas(monkeypatch):
    many = json.dumps({"keywords": [{"keyword": f"keyword {i}"} for i in range(sks.MAX_KEYWORD_IDEAS + 10)]})
    monkeypatch.setattr(sks._llm_client, "chat", AsyncMock(return_value=_fake_llm_response(many)))

    ideas = await sks.generate_keyword_ideas(_website(), [_page()])

    assert len(ideas) == sks.MAX_KEYWORD_IDEAS


def test_prompt_response_schema_has_no_volume_cpc_or_competition_field():
    """The whole point of Stage 9's design -- the JSON shape the LLM is
    asked to fill in has no volume/cpc/competition field at all, so it has
    nothing to hallucinate a number into. (The prompt's prose DOES mention
    "volume"/"competition" -- explicitly telling the model NOT to guess
    them -- so this checks the actual response schema, not prompt wording.)
    """
    schema_start = sks._SYSTEM_PROMPT.index('{"keywords"')
    schema = sks._SYSTEM_PROMPT[schema_start:].lower()
    assert "volume" not in schema
    assert "cpc" not in schema
    assert "competition" not in schema


def test_persist_keyword_opportunities_always_sets_not_available_volume(db_session, business):
    from app.models.seo_audit import SeoAudit
    from app.models.seo_website import SeoWebsite

    website = SeoWebsite(business_id=business["business_id"], url="https://greenleaf.test", crawl_tier="starter")
    db_session.add(website)
    db_session.commit()
    audit = SeoAudit(website_id=website.id, business_id=business["business_id"], status="completed")
    db_session.add(audit)
    db_session.commit()

    ideas = [sks.KeywordIdea(
        keyword="organic coffee oslo", intent="commercial", suggested_page="https://x/",
        current_page=None, content_gap="No page covers this.", recommendation="Write one.",
    )]

    rows = sks.persist_keyword_opportunities(db_session, audit.id, business["business_id"], ideas)
    db_session.commit()

    assert len(rows) == 1
    assert rows[0].volume == "Not available"
    assert rows[0].keyword == "organic coffee oslo"


def test_persist_ignores_any_llm_attempt_to_set_a_volume_field():
    """Even if a caller somehow constructed a KeywordIdea from an LLM
    response that tried to smuggle in a volume number, KeywordIdea itself
    has no volume field to carry it -- persist always writes the literal
    "Not available" string, never anything derived from the LLM output."""
    idea = sks.KeywordIdea(
        keyword="x", intent=None, suggested_page=None, current_page=None, content_gap=None, recommendation=None,
    )
    assert not hasattr(idea, "volume")
