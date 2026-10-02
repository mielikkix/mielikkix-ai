"""QA 2026-10-02 (E9, D7): flag FAQs and products that contradict each other."""

import json

from app.models.faq import FAQ
from app.models.product import Product


def test_flags_near_duplicate_faqs_with_different_answers_and_product_price_clashes(client, business, db_session):
    bid = business["business_id"]
    same = json.dumps([1.0, 0.0, 0.0])
    db_session.add_all([
        FAQ(business_id=bid, question="Can I pay yearly?", answer="Yes, 2 months free.", embedding_json=same),
        FAQ(business_id=bid, question="Can I pay for a year up front?", answer="No, monthly only.", embedding_json=json.dumps([0.99, 0.05, 0.0])),
        FAQ(business_id=bid, question="Do you deliver?", answer="Yes, in Oslo.", embedding_json=json.dumps([0.0, 1.0, 0.0])),
        Product(business_id=bid, name="Business plan", price=990, currency="NOK"),
        Product(business_id=bid, name="business plan", price=48, currency="USD"),
        Product(business_id=bid, name="Start plan", price=490, currency="NOK"),
    ])
    db_session.commit()

    issues = client.get("/api/faqs/issues", headers=business["headers"]).json()

    kinds = sorted(i["kind"] for i in issues)
    assert kinds == ["product_price_mismatch", "similar_faqs"]
    faq_issue = next(i for i in issues if i["kind"] == "similar_faqs")
    assert {it["question"] for it in faq_issue["items"]} == {"Can I pay yearly?", "Can I pay for a year up front?"}


def test_no_issues_for_consistent_knowledge(client, business, db_session):
    bid = business["business_id"]
    db_session.add_all([
        FAQ(business_id=bid, question="Opening hours?", answer="9-17.", embedding_json=json.dumps([1.0, 0.0])),
        FAQ(business_id=bid, question="Where are you?", answer="Oslo.", embedding_json=json.dumps([0.0, 1.0])),
    ])
    db_session.commit()

    assert client.get("/api/faqs/issues", headers=business["headers"]).json() == []
