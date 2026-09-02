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
from ..models.seo_draft import SeoDraft
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


def _content_prompt(name: str, category: str | None, description: str | None) -> str:
    return (
        f"Name: {name}\n"
        f"Category: {category or '(none given)'}\n"
        f"Current description: {description or '(none given)'}"
    )


async def _generate_content(name: str, category: str | None, description: str | None) -> DraftContent:
    result = await _llm_client.chat(
        [
            {"role": "system", "content": _SYSTEM_PROMPT},
            {"role": "user", "content": _content_prompt(name, category, description)},
        ],
        json_mode=True,
        max_tokens=1024,
    )
    return DraftContent(**json.loads(result.text))


async def _generate_one(product: Product) -> DraftContent:
    # The LLM call itself is inside this try, not just the JSON parse below
    # -- confirmed live: a Groq rate-limit/network/timeout error here is NOT
    # a malformed-response problem, but must degrade the same way (skip this
    # one product, keep going) rather than raising uncaught and 500ing the
    # whole batch request over one product's failure. Same "one bad item
    # doesn't abort the rest" reasoning as agents_voice.py/agents_support.py's
    # own broad except-Exception around their LLM calls.
    try:
        return await _generate_content(product.name, product.category, product.description)
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


def list_drafts(db: Session, business_id: str, status: str | None = None) -> list[SeoDraft]:
    query = db.query(SeoDraft).filter(SeoDraft.business_id == business_id)
    if status:
        query = query.filter(SeoDraft.status == status)
    return query.order_by(SeoDraft.created_at.desc()).all()


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


async def run_public_demo(name: str, category: str | None, description: str | None) -> DraftContent:
    """Public, unauthenticated, and never persisted -- powers the
    /demo/seo-copywriter marketing page (see agents_seo.py's own /demo
    route). Unlike generate_drafts(), there's no real Product row here: a
    website visitor has no business account, so this takes the same
    name/category/description fields directly and reuses the exact
    _generate_content() call the real per-tenant path uses, same split
    review_service.run_public_demo() uses for its own /demo route.
    """
    return await _generate_content(name, category, description)
