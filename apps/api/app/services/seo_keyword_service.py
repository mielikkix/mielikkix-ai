"""SEO Audit & Optimization -- keyword opportunity engine (Stage 9 of
apps/agents/seo-copywriter/CLAUDE.md, Phase 14). An LLM call, same "explain
over real data, never invent facts" boundary as
seo_recommendation_service.py's executive summary: the model is given the
website's real category/target market/seed keywords and its actual crawled
page titles/URLs (to spot real content gaps), and asked for keyword IDEAS
only.

Search volume/CPC/competition are ALWAYS "Not available" here -- never
asked of the LLM, and even if it ignored that and returned a number
anyway, this module discards it rather than storing it. No real
keyword-data API (DataForSEO/Ahrefs/SEMrush/etc.) is connected anywhere in
this codebase; inventing those numbers would be exactly the kind of
fabricated metric this agent's CLAUDE.md forbids. Revisit only if a real
data source is ever connected.
"""
import json
from dataclasses import dataclass
from typing import List, Optional

from mielikkix_agent_core import LLMClient
from mielikkix_agent_core.config import get_settings as get_agent_core_settings

from ..models.seo_audit import SeoCrawledPage, SeoKeywordOpportunity
from ..models.seo_website import SeoWebsite

# Same tier as the rest of this agent's LLM calls (apps/agents/CLAUDE.md:
# OpenAI cheap/fast tier for routine generation, not multi-step reasoning).
_llm_client = LLMClient(provider="openai", model=get_agent_core_settings().openai_mini_model)

MAX_KEYWORD_IDEAS = 15
# Bounds the prompt to a representative sample of the site, not its full
# page list -- keeps the call fast/cheap and avoids an unbounded prompt on
# a 500-page Advanced-tier audit.
MAX_PAGES_IN_PROMPT = 30

_SYSTEM_PROMPT = (
    "You are a keyword research assistant helping a business find real SEO "
    "keyword opportunities. You will be given the business's category, "
    "target country/language, any seed keywords they already have in mind, "
    "and a list of their actual existing page titles and URLs.\n\n"
    "Suggest up to 15 keyword opportunities. For each one, give:\n"
    "- keyword: a specific, realistic search phrase (never a single generic "
    "word)\n"
    "- intent: one of \"commercial\", \"informational\", \"local\", "
    "\"navigational\"\n"
    "- suggested_page: the URL from the existing page list that best "
    "matches this keyword, OR a short description of a NEW page to create "
    "if none of the existing pages fit\n"
    "- current_page: the exact URL from the existing page list if one "
    "already targets this keyword reasonably well, otherwise null\n"
    "- content_gap: a one-sentence description of what's missing (e.g. "
    "\"No existing page covers this topic\"), or null if an existing page "
    "already covers this keyword well\n"
    "- recommendation: one concrete sentence on what to do\n\n"
    "IMPORTANT: You have no access to real search volume, CPC, or "
    "competition data. Do NOT include those fields, do NOT estimate or "
    "guess numbers for them, and do NOT claim a keyword is 'high volume' "
    "or similar -- only suggest realistic, relevant keywords for this "
    "specific business.\n\n"
    "Respond with ONLY a JSON object (no other text before or after it), "
    'in exactly this shape: {"keywords": [{"keyword": "...", "intent": '
    '"...", "suggested_page": "...", "current_page": "..." | null, '
    '"content_gap": "..." | null, "recommendation": "..."}]}'
)


@dataclass
class KeywordIdea:
    keyword: str
    intent: Optional[str]
    suggested_page: Optional[str]
    current_page: Optional[str]
    content_gap: Optional[str]
    recommendation: Optional[str]


class KeywordGenerationError(Exception):
    """Raised when the LLM call/response fails -- caught by
    generate_keyword_opportunities so a failed keyword pass doesn't fail
    the whole audit (same "one bad thing doesn't abort the rest" rule as
    every other LLM call in this agent)."""


def _build_prompt(website: SeoWebsite, pages: List[SeoCrawledPage]) -> str:
    lines = []
    if website.primary_category:
        lines.append(f"Business category: {website.primary_category}")
    if website.target_country:
        lines.append(f"Target country: {website.target_country}")
    if website.target_language:
        lines.append(f"Target language: {website.target_language}")
    if website.target_keywords:
        lines.append(f"Seed keywords the business already has in mind: {', '.join(website.target_keywords)}")

    lines.append("Existing pages (title -- URL):")
    real_pages = [p for p in pages if p.title]
    if not real_pages:
        lines.append("(none crawled with a usable title)")
    for page in real_pages[:MAX_PAGES_IN_PROMPT]:
        lines.append(f"- {page.title} -- {page.url}")

    return "\n".join(lines)


def _parse_ideas(raw_json: str) -> List[KeywordIdea]:
    parsed = json.loads(raw_json)
    raw_ideas = parsed.get("keywords")
    if not isinstance(raw_ideas, list):
        raise ValueError("Response missing a 'keywords' list")

    ideas = []
    for item in raw_ideas[:MAX_KEYWORD_IDEAS]:
        keyword = item.get("keyword")
        if not isinstance(keyword, str) or not keyword.strip():
            continue  # skip a malformed individual entry rather than failing the whole batch
        ideas.append(KeywordIdea(
            keyword=keyword.strip(),
            intent=item.get("intent") if isinstance(item.get("intent"), str) else None,
            suggested_page=item.get("suggested_page") if isinstance(item.get("suggested_page"), str) else None,
            current_page=item.get("current_page") if isinstance(item.get("current_page"), str) else None,
            content_gap=item.get("content_gap") if isinstance(item.get("content_gap"), str) else None,
            recommendation=item.get("recommendation") if isinstance(item.get("recommendation"), str) else None,
        ))
    return ideas


async def generate_keyword_ideas(website: SeoWebsite, pages: List[SeoCrawledPage]) -> List[KeywordIdea]:
    """Pure generation, no DB writes -- see persist_keyword_opportunities
    for turning these into SeoKeywordOpportunity rows. Raises
    KeywordGenerationError on any LLM/parse failure; callers decide how to
    degrade (run_audit treats a failed keyword pass as "no ideas this
    time", not an audit failure)."""
    try:
        result = await _llm_client.chat(
            [
                {"role": "system", "content": _SYSTEM_PROMPT},
                {"role": "user", "content": _build_prompt(website, pages)},
            ],
            json_mode=True,
            max_tokens=2048,
        )
        return _parse_ideas(result.text)
    except Exception as exc:
        raise KeywordGenerationError(f"Could not generate keyword opportunities: {exc}") from exc


def persist_keyword_opportunities(db, audit_id, business_id, ideas: List[KeywordIdea]) -> List[SeoKeywordOpportunity]:
    rows = []
    for idea in ideas:
        row = SeoKeywordOpportunity(
            audit_id=audit_id,
            business_id=business_id,
            keyword=idea.keyword,
            intent=idea.intent,
            suggested_page=idea.suggested_page,
            current_page=idea.current_page,
            content_gap=idea.content_gap,
            recommendation=idea.recommendation,
            # Never set from the LLM's own output -- see this module's
            # docstring. Always literally "Not available" until a real
            # keyword-data API is ever connected.
            volume="Not available",
        )
        db.add(row)
        rows.append(row)
    return rows
