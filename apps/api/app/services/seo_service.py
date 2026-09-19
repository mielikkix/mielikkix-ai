"""SEO Copywriter -- see apps/agents/seo-copywriter/CLAUDE.md for the full
spec. Generates draft product descriptions + SEO metadata for a business's
own catalog, always into a separate SeoDraft row -- never straight onto the
live Product record (see that CLAUDE.md: silently overwriting live,
customer-facing copy without review is the one failure mode this agent must
never have). A human explicitly approves or rejects each draft.

Python note for a reader coming from TS/Angular: `@dataclass` here plays the
same role a plain TS `interface`/class-with-no-methods does -- a typed bag
of fields, with `__init__`/`__eq__`/`__repr__` generated for you instead of
hand-written.
"""

import json
from dataclasses import dataclass

from sqlalchemy.orm import Session

from mielikkix_agent_core import LLMClient
from mielikkix_agent_core.config import get_settings as get_agent_core_settings

from ..models.product import Product, product_embedding_text
from ..models.seo_audit import SeoAudit, SeoCrawledPage, SeoFinding
from ..models.seo_draft import SeoDraft
from ..models.seo_website import SeoWebsite
from ..rag.embeddings import embed_query

# SEO Copywriter's model tier: OpenAI's cheap/fast tier
# (settings.openai_mini_model, default gpt-4o-mini) -- routine, low-stakes
# content generation from a product's own existing name/category/
# description, not multi-step reasoning, so it doesn't need a
# higher-reasoning tier's cost.
_llm_client = LLMClient(provider="openai", model=get_agent_core_settings().openai_mini_model)

_SYSTEM_PROMPT = (
    "You write product copy that actually targets real search intent -- "
    "specific, concrete, and grounded in the product's real details, never "
    "generic keyword-stuffed filler. Given a product's name, category, and "
    "current description, write:\n"
    "- a rewritten product description (2-4 sentences, natural, persuasive, "
    "mentioning concrete details a shopper or search engine would care "
    "about)\n"
    "- an SEO title tag (under 60 characters, includes the product name)\n"
    "- a meta description (under 155 characters, a compelling one-line "
    "summary that would make someone click through from a search result)\n\n"
    "Respond with ONLY a JSON object (no other text before or after it), in "
    "exactly this shape:\n"
    '{"description": "<rewritten description>", "seo_title": "<title tag>", '
    '"meta_description": "<meta description>"}'
)


@dataclass
class DraftContent:
    description: str
    seo_title: str
    meta_description: str


class DraftGenerationError(Exception):
    """Raised when the LLM's JSON response doesn't parse into the shape
    DraftContent expects -- caught by generate_drafts() per-product so one
    bad response doesn't abort the whole batch."""


class UnsupportedFindingError(Exception):
    """Raised when a finding's rule_code has no Copywriter action wired up
    yet. Deliberately NOT wired up (Stage 7 of this agent's CLAUDE.md):
    images_missing_alt (we only store a per-page COUNT of images missing
    alt text, not each image's own src/context -- generating real alt text
    needs to know what a specific image actually shows, which nothing in
    this codebase captures yet) and duplicate_title/duplicate_content
    (fixing these requires a human choosing which of several pages keeps
    which copy, not a single generated answer for one page in isolation)."""


def _product_prompt(product: Product) -> str:
    return (
        f"Name: {product.name}\n"
        f"Category: {product.category or '(none given)'}\n"
        f"Current description: {product.description or '(none given)'}"
    )


async def _generate_one(product: Product) -> DraftContent:
    # The LLM call itself is inside this try, not just the JSON parse below
    # -- confirmed live: a Groq rate-limit/network/timeout error here is NOT
    # a malformed-response problem, but must degrade the same way (skip this
    # one product, keep going) rather than raising uncaught and 500ing the
    # whole batch request over one product's failure. Same "one bad item
    # doesn't abort the rest" reasoning as agents_voice.py/agents_support.py's
    # own broad except-Exception around their LLM calls.
    try:
        result = await _llm_client.chat(
            [
                {"role": "system", "content": _SYSTEM_PROMPT},
                {"role": "user", "content": _product_prompt(product)},
            ],
            json_mode=True,
            max_tokens=1024,
        )
        return DraftContent(**json.loads(result.text))
    except Exception as exc:
        raise DraftGenerationError(f"Could not generate an SEO draft for product {product.id}: {exc}") from exc


async def generate_drafts(db: Session, business_id: str, product_ids: list[str]) -> list[SeoDraft]:
    """Generates one draft per product ID, skipping any that don't belong
    to this business (defense against a stale/tampered ID list from the
    client) and any the LLM fails to produce valid JSON for (logged via the
    caller's own error handling, not raised -- one bad product shouldn't
    abort the rest of the batch). Runs sequentially, not concurrently: this
    is an explicit "generate for my selected products" action a human
    triggers and waits on, not a background job (see this agent's CLAUDE.md,
    "Real-time or batch?" -- no job queue exists in this codebase yet, so
    this mirrors documents.py's own crawl-and-ingest pattern of running
    synchronously inside a FastAPI BackgroundTasks call).
    """
    products = (
        db.query(Product)
        .filter(Product.business_id == business_id, Product.id.in_(product_ids))
        .all()
    )

    drafts = []
    for product in products:
        try:
            content = await _generate_one(product)
        except DraftGenerationError:
            continue
        draft = SeoDraft(
            business_id=business_id,
            product_id=product.id,
            draft_description=content.description,
            draft_seo_title=content.seo_title,
            draft_meta_description=content.meta_description,
        )
        db.add(draft)
        drafts.append(draft)

    db.commit()
    for draft in drafts:
        db.refresh(draft)
    return drafts


# ---------------------------------------------------------------------------
# Stage 7 (apps/agents/seo-copywriter/CLAUDE.md): generating a draft FROM an
# SEO Audit finding, instead of from the product picker above. Each
# supported rule_code maps to exactly one field the Copywriter fills in --
# never the full description+title+meta bundle generate_drafts() above
# produces, since a finding is about one specific, narrow problem.
# ---------------------------------------------------------------------------

_TITLE_RULE_CODES = {"missing_title", "title_too_long", "title_too_short"}
_META_RULE_CODES = {"missing_meta_description", "meta_description_too_long", "meta_description_too_short"}
_CONTENT_RULE_CODES = {"thin_content"}

_TITLE_SYSTEM_PROMPT = (
    "You write SEO title tags that target real search intent -- specific and "
    "concrete, never generic keyword-stuffed filler. Given a page's URL, its "
    "current title, and business context, write ONE new title tag, under 60 "
    "characters, that accurately describes what the page is actually about.\n\n"
    "Respond with ONLY a JSON object (no other text before or after it), in "
    'exactly this shape: {"seo_title": "<title tag>"}'
)

_META_SYSTEM_PROMPT = (
    "You write meta descriptions that earn real clicks from search results -- "
    "specific and concrete, never generic filler. Given a page's URL, its "
    "current title/meta description, and business context, write ONE new "
    "meta description, under 155 characters, that summarizes the page and "
    "gives a genuine reason to click through.\n\n"
    "Respond with ONLY a JSON object (no other text before or after it), in "
    'exactly this shape: {"meta_description": "<meta description>"}'
)

_CONTENT_SYSTEM_PROMPT = (
    "This page was flagged for thin content (very little visible text). You "
    "are drafting a brief to help expand it, NOT the final page copy. Given "
    "the page's URL, current title, and business context, write 2-4 "
    "sentences suggesting specific, concrete topics or details this page "
    "should cover to become genuinely useful -- never generic filler advice "
    "like 'add more content'.\n\n"
    "Respond with ONLY a JSON object (no other text before or after it), in "
    'exactly this shape: {"content_suggestion": "<suggestion>"}'
)


def _page_and_website_context(db: Session, finding: SeoFinding) -> tuple[SeoCrawledPage | None, SeoWebsite | None]:
    audit = db.query(SeoAudit).filter(SeoAudit.id == finding.audit_id).first()
    if audit is None:
        return None, None
    website = db.query(SeoWebsite).filter(SeoWebsite.id == audit.website_id).first()
    page = None
    if finding.affected_url:
        page = (
            db.query(SeoCrawledPage)
            .filter(SeoCrawledPage.audit_id == audit.id, SeoCrawledPage.url == finding.affected_url)
            .first()
        )
    return page, website


def _finding_prompt(finding: SeoFinding, page: SeoCrawledPage | None, website: SeoWebsite | None) -> str:
    lines = [f"Page URL: {finding.affected_url or '(unknown)'}"]
    if page is not None:
        lines.append(f"Current title: {page.title or '(none)'}")
        lines.append(f"Current meta description: {page.meta_description or '(none)'}")
        lines.append(f"Approximate word count: {page.word_count}")
    if website is not None:
        if website.primary_category:
            lines.append(f"Business category: {website.primary_category}")
        if website.target_country:
            lines.append(f"Target country: {website.target_country}")
        if website.target_language:
            lines.append(f"Target language: {website.target_language}")
        if website.target_keywords:
            lines.append(f"Target keywords: {', '.join(website.target_keywords)}")
    lines.append(f"Issue found: {finding.issue}")
    return "\n".join(lines)


async def _generate_field(system_prompt: str, user_prompt: str, field_name: str) -> str:
    try:
        result = await _llm_client.chat(
            [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            json_mode=True,
            max_tokens=512,
        )
        parsed = json.loads(result.text)
        value = parsed.get(field_name)
        if not isinstance(value, str) or not value.strip():
            raise ValueError(f"Response missing a usable '{field_name}'")
        return value.strip()
    except Exception as exc:
        raise DraftGenerationError(f"Could not generate {field_name}: {exc}") from exc


async def generate_draft_for_finding(db: Session, business_id: str, finding_id: str) -> SeoDraft:
    """Stage 7: the Copywriter's other entry point, alongside the product-
    picker flow above -- generates ONE piece of copy targeted at a specific
    audit finding. Always a new SeoDraft row, same "never write live
    without approval" rule as generate_drafts(); approve_draft only has
    somewhere to actually publish this to if it also ends up linked to a
    real Product (it never is, from this entry point, since findings are
    about crawled pages, not our own Product rows) -- otherwise approving
    just marks it ready for the business to use themselves.

    Raises (never swallows, unlike the batch flow above) -- this is a
    single, explicit, human-triggered action, so a failure should be
    reported, not silently skipped:
    - ValueError if the finding doesn't exist for this business.
    - UnsupportedFindingError if this rule_code has no Copywriter action.
    - DraftGenerationError if the LLM call/response itself fails.
    """
    finding = (
        db.query(SeoFinding)
        .filter(SeoFinding.id == finding_id, SeoFinding.business_id == business_id)
        .first()
    )
    if finding is None:
        raise ValueError(f"No finding {finding_id} for this business")

    if finding.rule_code in _TITLE_RULE_CODES:
        draft_type = "title"
    elif finding.rule_code in _META_RULE_CODES:
        draft_type = "meta_description"
    elif finding.rule_code in _CONTENT_RULE_CODES:
        draft_type = "content"
    else:
        raise UnsupportedFindingError(f"No Copywriter action is wired up yet for '{finding.rule_code}' findings.")

    page, website = _page_and_website_context(db, finding)
    prompt = _finding_prompt(finding, page, website)

    draft = SeoDraft(business_id=business_id, finding_id=finding.id, url=finding.affected_url, draft_type=draft_type)
    if draft_type == "title":
        draft.draft_seo_title = await _generate_field(_TITLE_SYSTEM_PROMPT, prompt, "seo_title")
    elif draft_type == "meta_description":
        draft.draft_meta_description = await _generate_field(_META_SYSTEM_PROMPT, prompt, "meta_description")
    else:
        draft.draft_description = await _generate_field(_CONTENT_SYSTEM_PROMPT, prompt, "content_suggestion")

    db.add(draft)
    db.commit()
    db.refresh(draft)
    return draft


def list_drafts(db: Session, business_id: str, status: str | None = None) -> list[SeoDraft]:
    query = db.query(SeoDraft).filter(SeoDraft.business_id == business_id)
    if status:
        query = query.filter(SeoDraft.status == status)
    return query.order_by(SeoDraft.created_at.desc()).all()


def list_drafts_for_finding(db: Session, business_id: str, finding_id: str) -> list[SeoDraft]:
    """The SEO Draft Workspace's per-finding view (Stage 7, Phase 13) --
    every draft ever generated for one specific finding, most recent
    first, so re-generating after a reject still shows the history."""
    return (
        db.query(SeoDraft)
        .filter(SeoDraft.business_id == business_id, SeoDraft.finding_id == finding_id)
        .order_by(SeoDraft.created_at.desc())
        .all()
    )


def approve_draft(db: Session, business_id: str, draft_id: str) -> SeoDraft | None:
    """Copies the draft onto the real Product record -- the only path that
    ever writes SEO Copywriter's output somewhere customer-facing. Also
    recomputes Product.embedding_json (same helper products.py's own
    create/update routes use) so RAG search over this product stays in
    sync with its new description -- an easy thing to forget since nothing
    enforces it at the database level, but a stale embedding after an
    approved rewrite would mean the chat widget/voice agent are grounding
    answers in the OLD description this replaced.
    """
    draft = (
        db.query(SeoDraft)
        .filter(SeoDraft.id == draft_id, SeoDraft.business_id == business_id)
        .first()
    )
    if draft is None:
        return None

    product = db.query(Product).filter(Product.id == draft.product_id).first()
    if product is not None:
        product.description = draft.draft_description
        product.seo_title = draft.draft_seo_title
        product.meta_description = draft.draft_meta_description
        product.embedding_json = json.dumps(embed_query(product_embedding_text(product)))

    draft.status = "approved"
    db.commit()
    db.refresh(draft)
    return draft


def reject_draft(db: Session, business_id: str, draft_id: str) -> SeoDraft | None:
    draft = (
        db.query(SeoDraft)
        .filter(SeoDraft.id == draft_id, SeoDraft.business_id == business_id)
        .first()
    )
    if draft is None:
        return None
    draft.status = "rejected"
    db.commit()
    db.refresh(draft)
    return draft
