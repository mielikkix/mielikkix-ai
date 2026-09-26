"""GDPR Phase 5: per-tenant conversation retention, visitor erasure, widget
privacy settings, voice AI disclosure, and no PII in logs."""
import asyncio
import logging
import uuid
from datetime import datetime, timedelta, timezone

import pytest
from mielikkix_agent_core import ToolCall

from app.api import agents_voice
from app.core.log_redaction import redact
from app.models.business import BusinessSettings
from app.models.conversation import Conversation, Message
from app.models.lead import Lead
from app.services import retention_service

NOW = datetime(2026, 9, 26, 12, 0, tzinfo=timezone.utc)


def _conv(db, business_id, started_days_ago, last_message_days_ago=None, session_id=None):
    conv = Conversation(
        business_id=business_id,
        session_id=session_id or f"sess_{uuid.uuid4().hex[:8]}",
        started_at=NOW - timedelta(days=started_days_ago),
    )
    db.add(conv)
    db.flush()
    if last_message_days_ago is not None:
        db.add(Message(conversation_id=conv.id, sender="visitor", content="hi", created_at=NOW - timedelta(days=last_message_days_ago)))
    db.commit()
    return conv.id


def _settings(db, business_id):
    return db.query(BusinessSettings).filter(BusinessSettings.business_id == uuid.UUID(str(business_id))).one()


# --- settings API ----------------------------------------------------------------

@pytest.mark.parametrize("bad", [0, 366, -5, "unlimited", True, 90.5])
def test_retention_cannot_be_out_of_bounds_or_unlimited(client, business, bad):
    resp = client.patch("/api/businesses/me/settings", json={"conversation_retention_days": bad}, headers=business["headers"])
    assert resp.status_code == 422


def test_retention_default_and_update(client, business):
    h = business["headers"]
    assert client.get("/api/businesses/me/settings", headers=h).json()["conversation_retention_days"] == 90
    resp = client.patch("/api/businesses/me/settings", json={"conversation_retention_days": 30}, headers=h)
    assert resp.status_code == 200 and resp.json()["conversation_retention_days"] == 30


@pytest.mark.parametrize("bad", ["javascript:alert(1)", "not a url", "ftp://x.no/p", "https://"])
def test_privacy_url_must_be_web_address(client, business, bad):
    resp = client.patch("/api/businesses/me/settings", json={"privacy_policy_url": bad}, headers=business["headers"])
    assert resp.status_code == 422


def test_privacy_url_is_public_and_clearable(client, business):
    h, bid = business["headers"], business["business_id"]
    client.patch("/api/businesses/me/settings", json={"privacy_policy_url": "https://shop.example/privacy"}, headers=h)
    assert client.get(f"/api/businesses/{bid}/public-settings").json()["privacy_policy_url"] == "https://shop.example/privacy"
    client.patch("/api/businesses/me/settings", json={"privacy_policy_url": ""}, headers=h)
    assert client.get(f"/api/businesses/{bid}/public-settings").json()["privacy_policy_url"] is None


# --- nightly retention ------------------------------------------------------------------

def test_expired_conversations_deleted_per_tenant_setting(client, db_session, signup):
    short, default = signup(), signup()
    s_bid, d_bid = uuid.UUID(short["business_id"]), uuid.UUID(default["business_id"])
    _settings(db_session, s_bid).conversation_retention_days = 30
    db_session.commit()

    old = _conv(db_session, s_bid, started_days_ago=100, last_message_days_ago=31)
    active = _conv(db_session, s_bid, started_days_ago=100, last_message_days_ago=1)  # old start, recent activity
    empty_old = _conv(db_session, s_bid, started_days_ago=40)
    boundary = _conv(db_session, s_bid, started_days_ago=29)
    other_tenant_old = _conv(db_session, d_bid, started_days_ago=60, last_message_days_ago=60)  # 60 < default 90
    other_tenant_expired = _conv(db_session, d_bid, started_days_ago=120, last_message_days_ago=91)

    lead = Lead(business_id=s_bid, conversation_id=old, name="Kari", email="kari@example.com")
    db_session.add(lead)
    db_session.commit()
    lead_id = lead.id

    deleted = retention_service.purge_expired_conversations(db_session, now=NOW)
    db_session.expire_all()
    remaining = {c.id for c in db_session.query(Conversation).all()}
    assert deleted == 3
    assert remaining == {active, boundary, other_tenant_old}
    assert db_session.query(Message).filter(Message.conversation_id.in_([old, other_tenant_expired])).count() == 0
    # The business's lead record survives; only its link to the deleted chat goes.
    kept = db_session.get(Lead, lead_id)
    assert kept is not None and kept.conversation_id is None


# --- visitor erasure -------------------------------------------------------------------------

def _lead(db, business_id, conv_id=None, **kw):
    lead = Lead(business_id=business_id, conversation_id=conv_id, name=kw.pop("name", "Visitor"), **kw)
    db.add(lead)
    db.commit()
    return lead.id


def test_erase_visitor_by_email_is_case_insensitive_and_tenant_scoped(client, db_session, signup):
    a, b = signup(), signup()
    a_bid, b_bid = uuid.UUID(a["business_id"]), uuid.UUID(b["business_id"])
    conv = _conv(db_session, a_bid, 1, 1)
    _lead(db_session, a_bid, conv, email="Kari@Example.com")
    _lead(db_session, a_bid, None, email="kari@example.com", name="Kari again")
    unrelated = _lead(db_session, a_bid, None, email="ola@example.com")
    other_biz_conv = _conv(db_session, b_bid, 1, 1)
    other_biz_lead = _lead(db_session, b_bid, other_biz_conv, email="kari@example.com")

    resp = client.post("/api/chat/visitors/erase", json={"email": "KARI@example.com "}, headers=a["headers"])
    assert resp.json() == {"leads_deleted": 2, "conversations_deleted": 1}
    db_session.expire_all()
    assert db_session.get(Conversation, conv) is None
    assert db_session.get(Lead, unrelated) is not None
    # Same person at ANOTHER business: untouched (that business is its own controller).
    assert db_session.get(Lead, other_biz_lead) is not None and db_session.get(Conversation, other_biz_conv) is not None


def test_erase_visitor_by_phone_session_and_lead(client, db_session, business):
    bid, h = uuid.UUID(business["business_id"]), business["headers"]
    _lead(db_session, bid, _conv(db_session, bid, 1, 1), phone="+47 912 34 567")
    resp = client.post("/api/chat/visitors/erase", json={"phone": "4791234567"}, headers=h).json()
    assert resp == {"leads_deleted": 1, "conversations_deleted": 1}

    _conv(db_session, bid, 1, 1, session_id="sess_abc")
    assert client.post("/api/chat/visitors/erase", json={"session_id": "sess_abc"}, headers=h).json()["conversations_deleted"] == 1

    conv = _conv(db_session, bid, 1, 1)
    name_only = _lead(db_session, bid, conv, name="No Contact Details")
    resp = client.post("/api/chat/visitors/erase", json={"lead_id": str(name_only)}, headers=h).json()
    assert resp == {"leads_deleted": 1, "conversations_deleted": 1}


def test_erase_requires_an_identifier_and_cannot_reach_other_tenants(client, db_session, signup):
    a, b = signup(), signup()
    assert client.post("/api/chat/visitors/erase", json={"email": "  "}, headers=a["headers"]).status_code == 422
    b_lead = _lead(db_session, uuid.UUID(b["business_id"]), None, email="x@example.com")
    resp = client.post("/api/chat/visitors/erase", json={"lead_id": str(b_lead)}, headers=a["headers"]).json()
    assert resp == {"leads_deleted": 0, "conversations_deleted": 0}
    assert db_session.get(Lead, b_lead) is not None


# --- voice ------------------------------------------------------------------------------------

def test_voice_greeting_discloses_ai_and_transcription():
    greeting = agents_voice._GREETING.lower()
    assert "ai assistant" in greeting
    assert "transcribed" in greeting and "isn't recorded" in greeting


def test_voice_tool_logs_contain_no_caller_pii(db_session, caplog, monkeypatch):
    call = "CA_test_pii"
    monkeypatch.setitem(agents_voice._call_pending_slots, call, [object(), object()])
    pii = {"name": "Kari Nordmann", "email": "kari.nordmann@example.com", "phone": "+47 912 34 567"}
    calls = [
        ToolCall(id="1", name="propose_booking", arguments='{"slot_index": 1, "name": "Kari Nordmann"}'),
        ToolCall(id="2", name="propose_booking", arguments='{"slot_index": 1, "name": "Kari Nordmann", "email": "kari.nordmann@"}'),
        ToolCall(id="3", name="propose_booking", arguments='{not json Kari Nordmann kari.nordmann@example.com'),
        ToolCall(id="4", name="create_support_ticket", arguments='{"customer_name": "Kari Nordmann"}'),
        ToolCall(id="5", name="unknown_tool", arguments='{"phone": "+47 912 34 567", "email": "kari.nordmann@example.com"}'),
    ]
    with caplog.at_level(logging.DEBUG, logger="app.api.agents_voice"):
        for tc in calls:
            asyncio.run(agents_voice._execute_tool(db_session, call, 1, "speech", tc, "en"))
    logged = "\n".join(r.getMessage() for r in caplog.records)
    assert logged  # the tools did log something
    for value in pii.values():
        assert value.lower() not in logged.lower(), value
    assert "kari" not in logged.lower()


def test_log_redaction_masks_emails_and_phones():
    assert redact('{"detail": "kari@example.com is already a list member, +47 912 34 567"}') == (
        '{"detail": "[email] is already a list member, [phone]"}'
    )
