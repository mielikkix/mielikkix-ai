"""Finds places where a business's own knowledge base may contradict itself,
so the chatbot doesn't pick one answer at random -- QA 2026-10-02 (E9, and D7:
two near-identical "Can I pay yearly..." FAQs with different answers).

Deliberately narrow and explainable: it flags candidates for the owner to
check, it never decides which answer is right.
"""

import json
import re
from dataclasses import dataclass, field

from sqlalchemy.orm import Session

from ..models.faq import FAQ
from ..models.product import Product
from ..rag.pipeline import _cosine_similarity

# Question embeddings this close are "the same question asked twice". Chosen
# conservatively: paraphrases score ~0.9+, merely related topics well below.
SIMILAR_QUESTION_THRESHOLD = 0.88
MAX_ISSUES = 20


@dataclass
class KnowledgeIssue:
    kind: str  # "similar_faqs" | "product_price_mismatch"
    message: str
    items: list[dict] = field(default_factory=list)


def _norm(text: str) -> str:
    return " ".join(re.findall(r"[\w']+", (text or "").lower()))


def find_issues(db: Session, business_id) -> list[KnowledgeIssue]:
    issues: list[KnowledgeIssue] = []

    faqs = db.query(FAQ).filter(FAQ.business_id == business_id, FAQ.is_active.isnot(False)).all()
    vectors = {}
    for faq in faqs:
        try:
            vectors[faq.id] = json.loads(faq.embedding_json) if faq.embedding_json else None
        except ValueError:
            vectors[faq.id] = None
    for i, a in enumerate(faqs):
        for b in faqs[i + 1:]:
            same = _norm(a.question) == _norm(b.question)
            if not same and vectors.get(a.id) and vectors.get(b.id):
                same = _cosine_similarity(vectors[a.id], vectors[b.id]) >= SIMILAR_QUESTION_THRESHOLD
            if same and _norm(a.answer) != _norm(b.answer):
                issues.append(
                    KnowledgeIssue(
                        kind="similar_faqs",
                        message="Two FAQs ask almost the same question but give different answers. Keep one, or make them agree.",
                        items=[
                            {"id": str(a.id), "question": a.question, "answer": a.answer},
                            {"id": str(b.id), "question": b.question, "answer": b.answer},
                        ],
                    )
                )

    by_name: dict[str, list[Product]] = {}
    for product in db.query(Product).filter(Product.business_id == business_id, Product.is_active.isnot(False)).all():
        by_name.setdefault(_norm(product.name), []).append(product)
    for products in by_name.values():
        prices = {(str(p.price) if p.price is not None else None, p.currency) for p in products}
        if len(products) > 1 and len(prices) > 1:
            issues.append(
                KnowledgeIssue(
                    kind="product_price_mismatch",
                    message=f'"{products[0].name}" is in your catalog more than once with different prices.',
                    items=[
                        {"id": str(p.id), "name": p.name, "price": str(p.price) if p.price is not None else None, "currency": p.currency}
                        for p in products
                    ],
                )
            )

    return issues[:MAX_ISSUES]
