import json
import math
import re
from typing import Dict, List, Tuple, Optional
from sqlalchemy.orm import Session
from ..models.document import DocumentChunk
from ..models.faq import FAQ
from ..models.product import Product
from ..models.llm_usage import LLMUsageLog
from .embeddings import embed_query
from .providers import get_llm_provider


def _cosine_similarity(a: List[float], b: List[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b))
    norm_a = math.sqrt(sum(x * x for x in a))
    norm_b = math.sqrt(sum(y * y for y in b))
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return dot / (norm_a * norm_b)


def retrieve_chunks(
    db: Session, business_id: str, query_embedding: List[float], top_k: int = 4
) -> List[Tuple[str, float]]:
    chunks = (
        db.query(DocumentChunk)
        .filter(DocumentChunk.business_id == business_id, DocumentChunk.embedding_json.isnot(None))
        .all()
    )
    scored = []
    for chunk in chunks:
        emb = json.loads(chunk.embedding_json)
        score = _cosine_similarity(query_embedding, emb)
        scored.append((chunk.content, score))
    scored.sort(key=lambda x: x[1], reverse=True)
    return scored[:top_k]


def retrieve_faqs(
    db: Session, business_id: str, query_embedding: List[float], top_k: int = 3
) -> List[Tuple[str, float]]:
    faqs = (
        db.query(FAQ)
        .filter(FAQ.business_id == business_id, FAQ.is_active == True, FAQ.embedding_json.isnot(None))
        .all()
    )
    scored = []
    for faq in faqs:
        emb = json.loads(faq.embedding_json)
        score = _cosine_similarity(query_embedding, emb)
        scored.append((f"Q: {faq.question}\nA: {faq.answer}", score))
    scored.sort(key=lambda x: x[1], reverse=True)
    return scored[:top_k]


def retrieve_products(
    db: Session, business_id: str, query_embedding: List[float], top_k: int = 5
) -> List[Tuple[str, float]]:
    products = (
        db.query(Product)
        .filter(Product.business_id == business_id, Product.is_active == True, Product.embedding_json.isnot(None))
        .all()
    )
    scored = []
    for product in products:
        emb = json.loads(product.embedding_json)
        score = _cosine_similarity(query_embedding, emb)
        price = f"{product.price} {product.currency}" if product.price is not None else "price not listed"
        line = f"Product: {product.name} — {price}"
        if product.description:
            line += f"\n{product.description}"
        scored.append((line, score))
    scored.sort(key=lambda x: x[1], reverse=True)
    return scored[:top_k]


def _build_contextual_query(history: List[Dict[str, str]], message: str) -> str:
    # A bare follow-up like "and the cappuccino?" has no anchor to what was
    # actually being asked (price? ingredients?), so retrieval on it alone
    # tends to score too low to match anything. Prepending the prior visitor
    # turn gives the embedding search that missing anchor back.
    prior_visitor_messages = [h["content"] for h in history if h.get("sender") == "visitor"]
    if prior_visitor_messages:
        return f"{prior_visitor_messages[-1]} {message}"
    return message


async def run_rag(
    db: Session,
    business_id: str,
    message: str,
    llm_provider: str = "groq",
    llm_model: Optional[str] = None,
    top_k: int = 4,
    confidence_threshold: float = 0.25,
    fallback_message: Optional[str] = None,
    tone: str = "friendly",
    history: Optional[List[Dict[str, str]]] = None,
    languages: Optional[List[str]] = None,
) -> Tuple[str, str, float]:
    history = history or []
    search_query = _build_contextual_query(history, message)

    query_emb = embed_query(search_query)
    chunks = retrieve_chunks(db, business_id, query_emb, top_k)
    faqs = retrieve_faqs(db, business_id, query_emb)
    products = retrieve_products(db, business_id, query_emb)
    all_matches = chunks + faqs + products

    # Previously only ever looked at chunk scores, so a business with a perfect,
    # exact FAQ match for the question but no matching document chunk still got
    # scored as low-confidence (triggering lead-capture suggestion) even though
    # the reply was fully grounded.
    best_score = max((score for _, score in all_matches), default=0.0)
    intent = _detect_intent(message)

    context_parts = [c for c, s in all_matches if s >= confidence_threshold]
    context = "\n\n".join(context_parts)

    if not context.strip():
        default_fallback = "I don't have specific information about that right now. Would you like me to connect you with our team?"
        return (fallback_message or default_fallback, intent, 0.0)

    provider = get_llm_provider(llm_provider, llm_model)
    reply = await provider.generate(message, context, tone, history, languages)
    log_llm_usage(db, business_id, llm_provider, provider, kind="chat")
    return reply, intent, best_score


def log_llm_usage(db: Session, business_id: str, provider_name: str, provider, kind: str) -> None:
    """Stage an LLMUsageLog row for the platform-admin usage dashboard, if
    the provider recorded token usage for its most recent call (only Groq
    does today -- see rag/providers/groq_provider.py). Not committed here;
    the caller's own db.commit() covers it in the same transaction."""
    usage = getattr(provider, "last_usage", None)
    if not usage:
        return
    db.add(LLMUsageLog(
        business_id=business_id,
        provider=provider_name,
        model=getattr(provider, "model", None),
        kind=kind,
        **usage,
    ))


def _matches_any(msg: str, keywords: List[str]) -> bool:
    """Whole-word match. Plain substring matching fired on ordinary words that
    merely contain a keyword -- "coffee" contains "fee", "locally" contains
    "call", "headphones" contains "phone" -- so for a cafe it mislabelled most
    questions as product_inquiry and popped the lead-capture form on questions
    that had nothing to do with getting in touch."""
    return any(re.search(rf"\b{re.escape(w)}\b", msg) for w in keywords)


def _detect_intent(message: str) -> str:
    msg = message.lower()
    if _matches_any(msg, ["price", "cost", "how much", "fee", "rate"]):
        return "product_inquiry"
    # "contact"/"call"/"email"/"reach"/"phone" alone missed plenty of obvious
    # buying/contact intent -- "I'd like to connect with your team", "can you
    # set up a demo", "I have a business proposal" all fell through to "faq"
    # and never triggered the lead-capture form.
    if _matches_any(msg, [
        "contact", "call", "email", "reach", "phone",
        "connect", "talk to", "speak to", "speak with",
        "get in touch", "reach out", "demo", "meeting", "proposal",
        "quote", "schedule",
    ]):
        return "lead"
    if _matches_any(msg, ["problem", "issue", "broken", "not working", "help"]):
        return "support"
    return "faq"
