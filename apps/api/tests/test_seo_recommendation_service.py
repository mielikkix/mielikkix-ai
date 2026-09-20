"""Tests for Stage 6 (apps/agents/seo-audit/CLAUDE.md): the
deterministic action-plan builder (no LLM, no DB) and the LLM-backed
executive summary. The LLM client is always mocked here -- no test makes
a real API call.
"""
import json
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.services import seo_recommendation_service as recs
from mielikkix_agent_core import LLMResult


def _finding(**overrides):
    defaults = dict(
        rule_code="missing_h1", severity="high", category="on_page",
        issue="Page has no H1 heading", affected_url="https://greenleaf.test/",
        explanation="The H1 is important.", recommended_fix="Add an H1.", status="open",
    )
    defaults.update(overrides)
    return SimpleNamespace(**defaults)


# ---------------------------------------------------------------------------
# build_action_plan
# ---------------------------------------------------------------------------

def test_groups_findings_by_rule_code():
    findings = [
        _finding(rule_code="missing_h1", affected_url="https://a"),
        _finding(rule_code="missing_h1", affected_url="https://b"),
        _finding(rule_code="missing_title", severity="high", affected_url="https://c"),
    ]
    plan = recs.build_action_plan(findings)
    assert len(plan) == 2
    h1_item = next(i for i in plan if i.rule_code == "missing_h1")
    assert set(h1_item.affected_urls) == {"https://a", "https://b"}


def test_critical_and_high_severity_map_to_priority_1():
    plan = recs.build_action_plan([_finding(rule_code="robots_blocks_entire_site", severity="critical")])
    assert plan[0].priority == 1
    plan = recs.build_action_plan([_finding(rule_code="missing_h1", severity="high")])
    assert plan[0].priority == 1


def test_medium_severity_maps_to_priority_2():
    plan = recs.build_action_plan([_finding(rule_code="thin_content", severity="medium")])
    assert plan[0].priority == 2


def test_low_and_informational_map_to_priority_3():
    plan = recs.build_action_plan([_finding(rule_code="missing_canonical", severity="low")])
    assert plan[0].priority == 3
    plan = recs.build_action_plan([_finding(rule_code="multiple_h1", severity="informational")])
    assert plan[0].priority == 3


def test_plan_sorted_by_priority_then_affected_count():
    findings = [
        _finding(rule_code="thin_content", severity="medium", affected_url="https://a"),
        _finding(rule_code="robots_blocks_entire_site", severity="critical", affected_url="https://b"),
        _finding(rule_code="missing_h1", severity="high", affected_url="https://c"),
        _finding(rule_code="missing_h1", severity="high", affected_url="https://d"),
    ]
    plan = recs.build_action_plan(findings)
    priorities = [item.priority for item in plan]
    assert priorities == sorted(priorities)
    assert plan[0].rule_code == "missing_h1"  # priority 1, 2 URLs -- ranks above the 1-URL critical item


def test_expected_benefit_and_difficulty_are_deterministic_lookups():
    item = recs.build_action_plan([_finding(rule_code="missing_h1", severity="high")])[0]
    assert item.expected_benefit == recs.EXPECTED_BENEFIT_BY_SEVERITY["high"]
    assert item.implementation_difficulty == "Easy"


def test_unmapped_rule_code_falls_back_to_moderate_difficulty():
    item = recs.build_action_plan([_finding(rule_code="some_future_rule", severity="medium")])[0]
    assert item.implementation_difficulty == "Moderate"


def test_status_is_the_shared_status_when_all_findings_agree():
    findings = [
        _finding(rule_code="missing_h1", status="ignored", affected_url="https://a"),
        _finding(rule_code="missing_h1", status="ignored", affected_url="https://b"),
    ]
    item = recs.build_action_plan(findings)[0]
    assert item.status == "ignored"


def test_status_defaults_to_open_when_findings_disagree():
    findings = [
        _finding(rule_code="missing_h1", status="ignored", affected_url="https://a"),
        _finding(rule_code="missing_h1", status="open", affected_url="https://b"),
    ]
    item = recs.build_action_plan(findings)[0]
    assert item.status == "open"


def test_empty_findings_list_produces_empty_plan():
    assert recs.build_action_plan([]) == []


def test_why_it_matters_and_recommended_action_come_from_the_finding():
    item = recs.build_action_plan([_finding(explanation="Because X.", recommended_fix="Do Y.")])[0]
    assert item.why_it_matters == "Because X."
    assert item.recommended_action == "Do Y."


# ---------------------------------------------------------------------------
# generate_executive_summary -- LLM call always mocked
# ---------------------------------------------------------------------------

def _fake_llm_response(json_text: str) -> LLMResult:
    return LLMResult(text=json_text, usage=None)


@pytest.mark.asyncio
async def test_empty_action_plan_never_calls_the_llm(monkeypatch):
    fake_chat = AsyncMock()
    monkeypatch.setattr(recs._llm_client, "chat", fake_chat)

    summary = await recs.generate_executive_summary(100, {"critical": 0, "high": 0, "medium": 0, "low": 0, "informational": 0}, [])

    assert summary is None
    fake_chat.assert_not_called()


@pytest.mark.asyncio
async def test_generate_executive_summary_returns_the_llms_text(monkeypatch):
    monkeypatch.setattr(
        recs._llm_client, "chat",
        AsyncMock(return_value=_fake_llm_response(json.dumps({"summary": "Fix the critical robots.txt issue first."}))),
    )
    plan = recs.build_action_plan([_finding(rule_code="robots_blocks_entire_site", severity="critical")])

    summary = await recs.generate_executive_summary(60, {"critical": 1, "high": 0, "medium": 0, "low": 0, "informational": 0}, plan)

    assert summary == "Fix the critical robots.txt issue first."


@pytest.mark.asyncio
async def test_malformed_llm_json_returns_none_not_a_crash(monkeypatch):
    monkeypatch.setattr(recs._llm_client, "chat", AsyncMock(return_value=_fake_llm_response("not json")))
    plan = recs.build_action_plan([_finding()])

    summary = await recs.generate_executive_summary(80, {"critical": 0, "high": 1, "medium": 0, "low": 0, "informational": 0}, plan)

    assert summary is None


@pytest.mark.asyncio
async def test_llm_call_failure_returns_none_not_a_crash(monkeypatch):
    monkeypatch.setattr(recs._llm_client, "chat", AsyncMock(side_effect=RuntimeError("provider is down")))
    plan = recs.build_action_plan([_finding()])

    summary = await recs.generate_executive_summary(80, {"critical": 0, "high": 1, "medium": 0, "low": 0, "informational": 0}, plan)

    assert summary is None


@pytest.mark.asyncio
async def test_empty_summary_string_is_treated_as_none(monkeypatch):
    monkeypatch.setattr(recs._llm_client, "chat", AsyncMock(return_value=_fake_llm_response(json.dumps({"summary": "   "}))))
    plan = recs.build_action_plan([_finding()])

    summary = await recs.generate_executive_summary(80, {"critical": 0, "high": 1, "medium": 0, "low": 0, "informational": 0}, plan)

    assert summary is None
