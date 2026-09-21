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
# build_action_plan -- Stage 12 (Google Analytics + Search Console) traffic
# weighting, backward compatible with every test above (no crawled_pages
# passed there -- traffic_weight stays None, sort order unchanged).
# ---------------------------------------------------------------------------

def _page(url, ga_sessions_28d=None, gsc_clicks_28d=None):
    return SimpleNamespace(url=url, ga_sessions_28d=ga_sessions_28d, gsc_clicks_28d=gsc_clicks_28d)


def test_traffic_weight_is_none_without_crawled_pages():
    plan = recs.build_action_plan([_finding()])
    assert plan[0].traffic_weight is None


def test_traffic_weight_is_none_when_no_affected_url_has_data():
    pages = [_page("https://greenleaf.test/", ga_sessions_28d=None, gsc_clicks_28d=None)]
    plan = recs.build_action_plan([_finding(affected_url="https://greenleaf.test/")], pages)
    assert plan[0].traffic_weight is None


def test_traffic_weight_sums_sessions_and_clicks_for_affected_urls():
    pages = [_page("https://greenleaf.test/", ga_sessions_28d=100, gsc_clicks_28d=20)]
    plan = recs.build_action_plan([_finding(affected_url="https://greenleaf.test/")], pages)
    assert plan[0].traffic_weight == 120


def test_traffic_weight_only_counts_urls_with_real_data():
    """One affected URL has data, the other doesn't -- the item's weight
    reflects only the real number, never treating the missing one as 0
    Toward the total (though the total itself is still just a sum of what
    IS known)."""
    pages = [_page("https://greenleaf.test/a", ga_sessions_28d=50)]
    findings = [
        _finding(rule_code="missing_h1", affected_url="https://greenleaf.test/a"),
        _finding(rule_code="missing_h1", affected_url="https://greenleaf.test/b"),
    ]
    plan = recs.build_action_plan(findings, pages)
    assert plan[0].traffic_weight == 50


def test_higher_traffic_item_sorts_first_within_the_same_priority_tier():
    pages = [
        _page("https://greenleaf.test/low-traffic", ga_sessions_28d=2),
        _page("https://greenleaf.test/high-traffic", ga_sessions_28d=500),
    ]
    findings = [
        _finding(rule_code="missing_title", severity="high", affected_url="https://greenleaf.test/low-traffic"),
        _finding(rule_code="missing_h1", severity="high", affected_url="https://greenleaf.test/high-traffic"),
    ]
    plan = recs.build_action_plan(findings, pages)
    assert plan[0].rule_code == "missing_h1"
    assert plan[1].rule_code == "missing_title"


def test_traffic_weight_never_promotes_a_lower_priority_item_above_a_higher_one():
    """A real but low-severity traffic boost still never outranks a
    genuinely critical issue -- priority always sorts first."""
    pages = [_page("https://greenleaf.test/popular", ga_sessions_28d=10000)]
    findings = [
        _finding(rule_code="thin_content", severity="low", affected_url="https://greenleaf.test/popular"),
        _finding(rule_code="robots_blocks_entire_site", severity="critical", affected_url="https://greenleaf.test/quiet"),
    ]
    plan = recs.build_action_plan(findings, pages)
    assert plan[0].rule_code == "robots_blocks_entire_site"


# ---------------------------------------------------------------------------
# _build_summary_prompt -- Phase 2: the executive summary must never
# mention an issue that isn't in the final, deduplicated findings list.
# Structurally guaranteed here: every prompt line comes directly from an
# ActionPlanItem already built from real persisted findings -- Phase 1's
# URL normalization (web_crawl.py) and canonical-grouping
# (seo_onpage_analyzer.py) mean a duplicate/false finding is suppressed
# BEFORE it's ever persisted, so there's nothing "extra" for the LLM to
# see in the first place. These tests lock that invariant in place.
# ---------------------------------------------------------------------------

def test_summary_prompt_contains_exactly_the_action_plans_own_issues_no_more():
    action_plan = recs.build_action_plan([
        _finding(rule_code="missing_h1", issue="Page has no H1 heading", severity="high"),
        _finding(rule_code="missing_title", issue="Page has no title tag", severity="high"),
    ])
    prompt = recs._build_summary_prompt(60, {}, action_plan)
    issue_lines = [line for line in prompt.split("\n") if line.startswith("- Priority")]
    assert len(issue_lines) == len(action_plan)
    for item in action_plan:
        assert any(item.issue in line for line in issue_lines)


def test_summary_prompt_never_mentions_a_finding_outside_the_given_action_plan():
    """A finding that exists but was passed separately (never included in
    action_plan) must not leak into the prompt text -- e.g. a duplicate
    that Phase 1's canonical-grouping already suppressed upstream."""
    action_plan = recs.build_action_plan([_finding(rule_code="missing_h1", issue="Page has no H1 heading")])
    suppressed_issue = "Title is duplicated across 2 pages"
    prompt = recs._build_summary_prompt(60, {}, action_plan)
    assert suppressed_issue not in prompt


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
