"""SEO Audit & Optimization -- recommendation engine (Stage 6 of
apps/agents/seo-audit/CLAUDE.md). This is the FIRST place in this
agent's pipeline that calls an LLM -- everything through Stage 5
(crawling, technical/on-page analysis, health scores) is deterministic.

Per that CLAUDE.md's Phase 18 hard boundary, the LLM here does exactly one
thing: write a short executive-summary narrative OVER facts that were
already deterministically established (finding counts, categories,
severities). It never decides whether something is broken, never adds a
new finding, and is fed nothing but aggregate counts and issue labels --
no full page content -- so it has nothing to hallucinate new facts from.

The prioritized action plan itself (Phase 11: Priority 1/2/3, "why it
matters", "recommended action", "expected benefit", "implementation
difficulty") is built entirely deterministically in build_action_plan()
below, from data already on each SeoFinding row plus two small fixed
lookup tables -- no LLM call needed for that part at all.
"""
import json
from dataclasses import dataclass
from typing import Dict, List, Optional

from mielikkix_agent_core import LLMClient
from mielikkix_agent_core.config import get_settings as get_agent_core_settings

from ..models.seo_audit import SeoFinding

# Same tier as the existing SEO Copywriter (apps/agents/CLAUDE.md: OpenAI
# cheap/fast tier for routine, low-stakes generation) -- summarizing a
# short list of already-known findings is not multi-step reasoning.
_llm_client = LLMClient(provider="openai", model=get_agent_core_settings().openai_mini_model)

# severity -> priority tier (Phase 11's Priority 1/Critical, 2/High,
# 3/Medium-and-below). A fixed mapping, not an LLM judgment call.
SEVERITY_TO_PRIORITY = {"critical": 1, "high": 1, "medium": 2, "low": 3, "informational": 3}

# severity -> a plain-language expected-benefit statement. Deterministic
# and deliberately generic (no invented percentages/numbers) -- this
# agent's CLAUDE.md forbids fabricated metrics.
EXPECTED_BENEFIT_BY_SEVERITY = {
    "critical": "High — resolves a site-wide indexing or crawlability blocker",
    "high": "High — meaningfully improves how search engines evaluate the affected pages",
    "medium": "Medium — improves search appearance or user experience",
    "low": "Low — minor polish",
    "informational": "Informational — review only, may already be intentional",
}

# rule_code -> a plain-language difficulty estimate, based on what the fix
# actually requires (a config/markup edit vs. real content work). Fixed
# lookup, not guessed per-audit -- unmapped codes fall back to "Moderate".
IMPLEMENTATION_DIFFICULTY_BY_RULE = {
    "robots_missing": "Easy",
    "robots_blocks_entire_site": "Easy",
    "robots_missing_sitemap_declaration": "Easy",
    "sitemap_missing": "Easy",
    "sitemap_url_blocked_by_robots": "Easy",
    "broken_page": "Moderate",
    "long_redirect_chain": "Easy",
    "page_excluded_from_indexing": "Easy",
    "missing_canonical": "Easy",
    "canonical_points_elsewhere": "Easy",
    "missing_title": "Easy",
    "title_too_long": "Easy",
    "title_too_short": "Easy",
    "missing_meta_description": "Easy",
    "meta_description_too_long": "Easy",
    "meta_description_too_short": "Easy",
    "missing_h1": "Easy",
    "multiple_h1": "Easy",
    "images_missing_alt": "Easy",
    "duplicate_title": "Moderate",
    "duplicate_meta_description": "Moderate",
    "thin_content": "Hard",
    "duplicate_content": "Hard",
}
_DEFAULT_DIFFICULTY = "Moderate"


@dataclass
class ActionPlanItem:
    priority: int  # 1, 2, or 3
    category: str
    rule_code: str
    issue: str
    affected_urls: List[str]
    why_it_matters: Optional[str]
    recommended_action: Optional[str]
    expected_benefit: str
    implementation_difficulty: str
    status: str  # "open" unless every underlying finding shares one other status
    # Stage 12 (Google Analytics + Search Console, see this agent's
    # CLAUDE.md "Professional tier roadmap") -- real sessions + clicks
    # summed across this item's own affected URLs, from whichever of them
    # actually had data. None (never 0) when no affected URL has any real
    # traffic data at all -- e.g. GA/Search Console aren't connected for
    # this business, exactly Stage 8's "absence isn't zero" rule. Used only
    # to break ties within the same priority tier (see build_action_plan's
    # sort key) -- it never changes an item's actual priority number,
    # since real-but-lower-severity traffic data still shouldn't outrank a
    # genuinely critical technical issue.
    traffic_weight: Optional[int] = None


def _traffic_weight_for_urls(urls: List[str], metrics_by_url: Dict[str, int]) -> Optional[int]:
    known = [metrics_by_url[u] for u in urls if u in metrics_by_url]
    return sum(known) if known else None


def _page_traffic_metrics(crawled_pages) -> Dict[str, int]:
    """url -> ga_sessions_28d + gsc_clicks_28d, for pages that have at
    least one of the two -- a page with neither is left OUT of this dict
    entirely (not given a 0), so _traffic_weight_for_urls above can tell
    "no data for this URL" apart from "confirmed zero traffic"."""
    metrics: Dict[str, int] = {}
    for page in crawled_pages or []:
        sessions = getattr(page, "ga_sessions_28d", None)
        clicks = getattr(page, "gsc_clicks_28d", None)
        if sessions is None and clicks is None:
            continue
        metrics[page.url] = (sessions or 0) + (clicks or 0)
    return metrics


def build_action_plan(findings: List[SeoFinding], crawled_pages=None) -> List[ActionPlanItem]:
    """Groups an audit's findings by rule_code into one action item per
    distinct issue type (e.g. one "duplicate_title" item listing every
    affected URL, not one item per URL) -- matches this agent's CLAUDE.md,
    Phase 11's roadmap shape. Sorted by priority, most urgent first, then
    (Stage 12) by real traffic weight when crawled_pages carries any --
    within the same priority tier, an issue affecting a page with real
    visits/clicks sorts above one affecting a page nobody visits.
    crawled_pages is optional and backward compatible: omit it (or pass
    pages with no ga_*/gsc_* data) and every item's traffic_weight is None,
    and the sort falls back to exactly its pre-Stage-12 behavior."""
    groups: Dict[str, List[SeoFinding]] = {}
    for finding in findings:
        groups.setdefault(finding.rule_code, []).append(finding)

    page_metrics = _page_traffic_metrics(crawled_pages)

    items: List[ActionPlanItem] = []
    for rule_code, group in groups.items():
        representative = group[0]
        statuses = {f.status for f in group}
        status = statuses.pop() if len(statuses) == 1 else "open"
        affected_urls = [f.affected_url for f in group if f.affected_url]

        items.append(ActionPlanItem(
            priority=SEVERITY_TO_PRIORITY.get(representative.severity, 3),
            category=representative.category,
            rule_code=rule_code,
            issue=representative.issue,
            affected_urls=affected_urls,
            why_it_matters=representative.explanation,
            recommended_action=representative.recommended_fix,
            expected_benefit=EXPECTED_BENEFIT_BY_SEVERITY.get(representative.severity, "Not available"),
            implementation_difficulty=IMPLEMENTATION_DIFFICULTY_BY_RULE.get(rule_code, _DEFAULT_DIFFICULTY),
            status=status,
            traffic_weight=_traffic_weight_for_urls(affected_urls, page_metrics),
        ))

    return sorted(
        items,
        key=lambda item: (item.priority, -(item.traffic_weight or 0), -len(item.affected_urls)),
    )


_SUMMARY_SYSTEM_PROMPT = (
    "You are summarizing a technical SEO audit for a business owner who is not an "
    "SEO expert. You will be given the audit's real, already-computed diagnostic "
    "scores and a list of issue types actually found, each with its severity and "
    "how many pages it affects. Write a short (3-5 sentence) plain-language "
    "executive summary of the overall state of the site and what to fix first.\n\n"
    "Rules:\n"
    "- Only reference issues actually listed below. Never invent an issue, a URL, "
    "or a number that wasn't given to you.\n"
    "- Do not state or imply a specific ranking-position or traffic outcome -- "
    "these scores are an internal diagnostic, not a Google ranking signal.\n"
    "- Be concrete: name the highest-priority issue type(s) by what they affect.\n\n"
    "Respond with ONLY a JSON object (no other text before or after it), in "
    'exactly this shape: {"summary": "<3-5 sentence summary>"}'
)


def _build_summary_prompt(overall_health: Optional[int], finding_counts: Dict[str, int], action_plan: List[ActionPlanItem]) -> str:
    lines = [
        f"Overall diagnostic score: {overall_health if overall_health is not None else 'not yet computed'}/100",
        f"Findings by severity: {finding_counts}",
        "Issue types found (priority, issue, pages affected):",
    ]
    for item in action_plan[:15]:  # bounded -- an executive summary doesn't need the long tail
        lines.append(f"- Priority {item.priority}: {item.issue} ({len(item.affected_urls)} page(s))")
    return "\n".join(lines)


async def generate_executive_summary(
    overall_health: Optional[int], finding_counts: Dict[str, int], action_plan: List[ActionPlanItem]
) -> Optional[str]:
    """Returns None (never a fabricated placeholder) if the LLM call fails
    or returns malformed JSON -- same "skip, don't fake it" rule
    seo_service.py's _generate_one already follows. A missing summary
    just means the audit's action plan/findings are shown without a
    narrative on top, which is still fully real, usable data."""
    if not action_plan:
        return None  # nothing to summarize -- a clean audit doesn't need a paragraph saying so

    try:
        result = await _llm_client.chat(
            [
                {"role": "system", "content": _SUMMARY_SYSTEM_PROMPT},
                {"role": "user", "content": _build_summary_prompt(overall_health, finding_counts, action_plan)},
            ],
            json_mode=True,
            max_tokens=400,
        )
        parsed = json.loads(result.text)
        summary = parsed.get("summary")
        return summary.strip() if isinstance(summary, str) and summary.strip() else None
    except Exception:
        return None
