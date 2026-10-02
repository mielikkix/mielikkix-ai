"""QA 2026-10-02: conversations can be closed/reopened and searched (D10/E3),
the dashboard's test chats never count (E4/E5), and Overview stats count
conversations rather than messages and skip noise (D10)."""

from app.api.analytics import top_visitor_questions
from app.services import chat_service


async def _fake_run_rag(**kwargs):
    return "a reply", "faq", 0.9


def _send(client, business, session, message):
    return client.post(
        "/api/chat/message",
        json={"business_id": business["business_id"], "session_id": session, "message": message},
    )


def test_close_and_reopen_and_visitor_reopens(client, business, monkeypatch):
    monkeypatch.setattr(chat_service, "run_rag", _fake_run_rag)
    h = business["headers"]
    _send(client, business, "s1", "What are your opening hours?")
    conv = client.get("/api/chat/conversations", headers=h).json()[0]

    closed = client.patch(f"/api/chat/conversations/{conv['id']}", json={"status": "closed"}, headers=h)
    assert closed.status_code == 200 and closed.json()["status"] == "closed"
    assert client.get("/api/chat/conversations", params={"status": "open"}, headers=h).json() == []

    # The visitor writing again reopens the SAME conversation (not a second one).
    _send(client, business, "s1", "And on Sundays?")
    convs = client.get("/api/chat/conversations", headers=h).json()
    assert len(convs) == 1 and convs[0]["status"] == "open"
    assert convs[0]["preview"] == "What are your opening hours?"
    assert convs[0]["language"] == "en"
    assert client.get("/api/businesses/me/plan", headers=h).json()["usage"]["conversations_this_month"] == 1

    assert client.patch(f"/api/chat/conversations/{conv['id']}", json={"status": "archived"}, headers=h).status_code == 422


def test_search_finds_conversations_by_message_text(client, business, monkeypatch):
    monkeypatch.setattr(chat_service, "run_rag", _fake_run_rag)
    h = business["headers"]
    _send(client, business, "a", "Do you deliver to Bergen?")
    _send(client, business, "b", "What does the Business plan cost?")

    hits = client.get("/api/chat/conversations", params={"q": "bergen"}, headers=h).json()

    assert [c["session_id"] for c in hits] == ["a"]


def test_dashboard_test_chats_never_count(client, business, monkeypatch):
    monkeypatch.setattr(chat_service, "run_rag", _fake_run_rag)
    h = business["headers"]

    resp = client.post("/api/chat/test", json={"session_id": "t1", "message": "How much is the Business plan?"}, headers=h)

    assert resp.status_code == 200 and resp.json()["reply"] == "a reply"
    assert client.get("/api/chat/conversations", headers=h).json() == []
    assert client.get("/api/businesses/me/plan", headers=h).json()["usage"]["conversations_this_month"] == 0
    assert client.get("/api/analytics/summary", headers=h).json()["conversation_count"] == 0
    # needs a login
    assert client.post("/api/chat/test", json={"session_id": "t1", "message": "hi"}).status_code == 401


def test_intent_breakdown_counts_conversations_not_messages(client, business, monkeypatch, set_plan):
    set_plan(business["business_id"], "business")
    monkeypatch.setattr(chat_service, "run_rag", _fake_run_rag)
    for message in ("What are your hours?", "And on Saturday?", "And on Sunday?"):
        _send(client, business, "one-visitor", message)

    summary = client.get("/api/analytics/summary", headers=business["headers"]).json()

    assert summary["conversation_count"] == 1
    assert summary["message_count"] == 3
    assert summary["intent_breakdown"] == {"faq": 1}


def test_top_questions_skip_noise_and_count_each_conversation_once():
    rows = [
        ("c1", "how?"), ("c2", "how?"), ("c3", "how?"),           # noise: one word
        ("c1", "What does it cost?"), ("c1", "what does it cost"),  # same visitor twice
        ("c2", "What does it COST?!"),
        ("c3", "Do you have parking?"),
    ]

    result = top_visitor_questions(rows)

    assert result[0] == ("What does it cost?", 2)
    assert ("Do you have parking?", 1) in result
    assert all("how" != q.strip("?").lower() for q, _ in result)
