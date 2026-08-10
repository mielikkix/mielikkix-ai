"""API-level tests for tiered analytics (app/api/analytics.py)."""
import uuid
from app.models.conversation import Conversation, Message


def seed_conversation(db_session, business_id, question, intent="faq"):
    conv = Conversation(business_id=business_id, session_id=uuid.uuid4().hex)
    db_session.add(conv)
    db_session.flush()
    db_session.add(Message(conversation_id=conv.id, sender="visitor", content=question))
    db_session.add(Message(conversation_id=conv.id, sender="ai", content="reply", intent=intent, confidence=0.9))
    db_session.commit()


def test_basic_tier_hides_top_questions_and_intent_breakdown(client, business, db_session):
    seed_conversation(db_session, business["business_id"], "What are your hours?")
    seed_conversation(db_session, business["business_id"], "What are your hours?")

    resp = client.get("/api/analytics/summary", headers=business["headers"])
    assert resp.status_code == 200
    body = resp.json()
    assert body["analytics_tier"] == "basic"
    assert body["top_questions"] == []
    assert body["intent_breakdown"] == {}
    # Headline counts are still available on every tier.
    assert body["conversation_count"] == 2
    assert body["message_count"] == 2


def test_standard_tier_shows_top_questions_but_not_intent_breakdown(client, business, db_session, set_plan):
    set_plan(business["business_id"], "basic")
    seed_conversation(db_session, business["business_id"], "What are your hours?")
    seed_conversation(db_session, business["business_id"], "What are your hours?")
    seed_conversation(db_session, business["business_id"], "Do you deliver?")

    resp = client.get("/api/analytics/summary", headers=business["headers"])
    body = resp.json()
    assert body["analytics_tier"] == "standard"
    assert body["top_questions"][0]["question"] == "What are your hours?"
    assert body["top_questions"][0]["count"] == 2
    assert body["intent_breakdown"] == {}


def test_advanced_tier_shows_intent_breakdown(client, business, db_session, set_plan):
    set_plan(business["business_id"], "business")
    seed_conversation(db_session, business["business_id"], "What are your hours?", intent="faq")
    seed_conversation(db_session, business["business_id"], "Do you sell mugs?", intent="product_inquiry")
    seed_conversation(db_session, business["business_id"], "Can I get a callback?", intent="lead")

    resp = client.get("/api/analytics/summary", headers=business["headers"])
    body = resp.json()
    assert body["analytics_tier"] == "advanced"
    assert body["top_questions"]  # still populated at this tier
    assert body["intent_breakdown"] == {"faq": 1, "product_inquiry": 1, "lead": 1}


def test_analytics_scoped_per_business(client, signup, db_session):
    biz_a = signup()
    biz_b = signup()
    seed_conversation(db_session, biz_a["business_id"], "Only A's question")

    resp = client.get("/api/analytics/summary", headers=biz_b["headers"])
    assert resp.json()["conversation_count"] == 0
