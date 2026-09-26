"""GDPR Phase 4: account self-service (export, deletion, marketing toggle,
consent history, Terms/DPA re-acceptance) and the minimised, time-limited
retention of consent records after deletion."""
import json
import os
import uuid
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import func, select

from app.core.config import settings
from app.core.database import Base
from app.core.legal import CONSENT_RETENTION_AFTER_DELETION_DAYS, DELETION_GRACE_DAYS
from app.models.business import Business
from app.models.consent_record import ConsentRecord
from app.models.conversation import Conversation, Message
from app.models.document import Document
from app.models.faq import FAQ
from app.models.lead import Lead
from app.models.password_reset_token import PasswordResetToken
from app.models.user import User
from app.services import account_service, consent_service


def _seed(db, business_id, user_id, upload_path=None):
    conv = Conversation(business_id=business_id, session_id=f"s-{uuid.uuid4()}")
    db.add_all([FAQ(business_id=business_id, question="Q?", answer="A.")])
    db.add(conv)
    db.flush()
    db.add(Message(conversation_id=conv.id, sender="user", content="hello, I'm Kari, 912 34 567"))
    db.add(Lead(business_id=business_id, conversation_id=conv.id, name="Kari Nordmann", email="kari@example.com"))
    db.add(PasswordResetToken(user_id=user_id, token_hash=uuid.uuid4().hex, expires_at=datetime.now(timezone.utc)))
    if upload_path:
        db.add(Document(business_id=business_id, filename="menu.pdf", file_url=upload_path, file_type="pdf", uploaded_by=user_id))
    db.commit()


def _user(db, business):
    return db.query(User).filter(User.email == business["email"]).one()


# --- export -----------------------------------------------------------------

def test_export_contains_account_and_tenant_data_without_secrets(client, db_session, business):
    user = _user(db_session, business)
    _seed(db_session, user.business_id, user.id)

    resp = client.get("/api/account/export", headers=business["headers"])
    assert resp.status_code == 200
    assert "attachment" in resp.headers["content-disposition"]
    data = resp.json()
    assert data["user"]["email"] == business["email"]
    assert {c["type"] for c in data["consent_history"]} == {"terms", "dpa", "age_confirmation", "marketing_email"}
    assert data["tables"]["faqs"][0]["question"] == "Q?"
    assert data["tables"]["messages"][0]["content"].startswith("hello")
    assert data["tables"]["leads"][0]["name"] == "Kari Nordmann"

    raw = json.dumps(data).lower()
    assert user.hashed_password.lower() not in raw
    assert "hashed_password" not in raw and "token_hash" not in raw and "api_key" not in raw


def test_export_never_includes_another_tenants_data(client, db_session, signup):
    a, b = signup(), signup()
    ub = _user(db_session, b)
    _seed(db_session, ub.business_id, ub.id)
    data = client.get("/api/account/export", headers=a["headers"]).json()
    assert data["tables"]["faqs"] == [] and data["tables"]["leads"] == [] and data["tables"]["messages"] == []
    assert b["email"] not in json.dumps(data)


# --- marketing toggle + history ------------------------------------------------

def test_marketing_toggle_records_grant_and_withdrawal(client, db_session, business):
    user = _user(db_session, business)
    on = client.put("/api/account/marketing", json={"subscribed": True}, headers=business["headers"]).json()
    assert on["marketing_emails"] is True
    off = client.put("/api/account/marketing", json={"subscribed": False}, headers=business["headers"]).json()
    assert off["marketing_emails"] is False
    assert not consent_service.has_marketing_consent(db_session, user.id)
    marketing = [h for h in off["history"] if h["type"] == "marketing_email"]
    assert [(h["granted"], h["source"]) for h in marketing] == [(False, "settings"), (True, "settings"), (False, "register")]
    assert marketing[1]["withdrawn_at"] is not None


# --- re-acceptance --------------------------------------------------------------

def test_terms_version_bump_forces_reacceptance(client, db_session, business, monkeypatch):
    monkeypatch.setattr(consent_service, "TERMS_VERSION", "terms-2099-01-01")
    h = business["headers"]

    me = client.get("/api/auth/me", headers=h).json()
    assert me["pending_acceptance"] == ["terms"]
    assert client.get("/api/businesses/me", headers=h).status_code == 403
    # Never conditional on accepting: export, marketing, deletion routes.
    assert client.get("/api/account/export", headers=h).status_code == 200
    assert client.put("/api/account/marketing", json={"subscribed": False}, headers=h).status_code == 200

    assert client.post("/api/account/consents/accept", json={"documents": []}, headers=h).status_code == 422
    resp = client.post("/api/account/consents/accept", json={"documents": ["terms"]}, headers=h)
    assert resp.status_code == 200 and resp.json()["pending_acceptance"] == []
    assert client.get("/api/businesses/me", headers=h).status_code == 200

    latest = consent_service.latest(db_session, _user(db_session, business).id, "terms")
    assert (latest.document_version, latest.source) == ("terms-2099-01-01", "reaccept")


def test_account_without_any_consent_records_must_accept(client, db_session, business):
    # Accounts created before sign-up consent existed have no rows at all.
    db_session.query(ConsentRecord).delete()
    db_session.commit()
    h = business["headers"]
    assert client.get("/api/auth/me", headers=h).json()["pending_acceptance"] == ["terms", "dpa"]
    assert client.get("/api/businesses/me", headers=h).status_code == 403
    client.post("/api/account/consents/accept", json={"documents": ["terms", "dpa"]}, headers=h)
    assert client.get("/api/businesses/me", headers=h).status_code == 200


# --- deletion request / cancel ------------------------------------------------------

def test_deletion_requires_exact_business_name(client, business):
    resp = client.post("/api/account/deletion", json={"confirm_business_name": "wrong"}, headers=business["headers"])
    assert resp.status_code == 400


def test_request_and_cancel_deletion(client, db_session, business):
    h = business["headers"]
    name = db_session.get(Business, uuid.UUID(business["business_id"])).name
    before = datetime.now(timezone.utc)
    body = client.post("/api/account/deletion", json={"confirm_business_name": name}, headers=h).json()
    scheduled = datetime.fromisoformat(body["deletion_scheduled_for"])
    assert timedelta(days=DELETION_GRACE_DAYS) - timedelta(minutes=1) < scheduled - before < timedelta(days=DELETION_GRACE_DAYS, minutes=1)
    # Can still sign in and use the dashboard during the grace period.
    assert client.get("/api/auth/me", headers=h).json()["deletion_scheduled_for"] is not None

    body = client.delete("/api/account/deletion", headers=h).json()
    assert body["deletion_scheduled_for"] is None
    # Cancelled: the nightly job, even far in the future, deletes nothing.
    account_service.purge_due(db_session, now=scheduled + timedelta(days=1))
    assert db_session.get(Business, uuid.UUID(business["business_id"])) is not None


def test_only_owner_can_delete(client, db_session, business):
    user = _user(db_session, business)
    user.role = "member"
    db_session.commit()
    resp = client.post("/api/account/deletion", json={"confirm_business_name": "x"}, headers=business["headers"])
    assert resp.status_code == 403


def test_platform_operator_account_cannot_self_delete(client, db_session, business, monkeypatch):
    monkeypatch.setattr(settings, "platform_admin_emails", business["email"])
    name = db_session.get(Business, uuid.UUID(business["business_id"])).name
    resp = client.post("/api/account/deletion", json={"confirm_business_name": name}, headers=business["headers"])
    assert resp.status_code == 400


# --- hard delete + minimised consent retention -----------------------------------------

@pytest.fixture()
def upload_dir(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "upload_dir", str(tmp_path))
    return tmp_path


def test_purge_deletes_all_tenant_data_and_minimises_consent(client, db_session, signup, upload_dir):
    victim, bystander = signup(), signup()
    v_user, b_user = _user(db_session, victim), _user(db_session, bystander)
    v_bid, v_uid, v_email = v_user.business_id, v_user.id, v_user.email
    upload = upload_dir / "victim-menu.pdf"
    upload.write_bytes(b"%PDF")
    _seed(db_session, v_bid, v_uid, upload_path=str(upload))
    _seed(db_session, b_user.business_id, b_user.id)
    client.put("/api/account/marketing", json={"subscribed": True}, headers=victim["headers"])
    client.put("/api/account/marketing", json={"subscribed": False}, headers=victim["headers"])

    name = db_session.get(Business, v_bid).name
    client.post("/api/account/deletion", json={"confirm_business_name": name}, headers=victim["headers"])
    scheduled = db_session.get(Business, v_bid).deletion_scheduled_for

    # Not due yet: nothing happens.
    account_service.purge_due(db_session, now=scheduled - timedelta(hours=1))
    assert db_session.get(Business, v_bid) is not None

    deleted_at = scheduled + timedelta(minutes=5)
    result = account_service.purge_due(db_session, now=deleted_at)
    assert result == [(name, [v_email])]
    db_session.expire_all()

    # Every tenant table is empty for the deleted business (including indirect
    # ones: messages, password_reset_tokens) ...
    assert db_session.get(Business, v_bid) is None
    for table, column, parent in account_service.tenant_tables():
        if parent is None:
            n = db_session.execute(select(func.count()).select_from(table).where(table.c.business_id == v_bid)).scalar()
            assert n == 0, table.name
    assert db_session.query(Message).count() == 1  # the bystander's
    assert db_session.query(PasswordResetToken).filter(PasswordResetToken.user_id == v_uid).count() == 0
    assert not upload.exists()
    # ... the bystander is untouched ...
    assert db_session.get(Business, b_user.business_id) is not None
    assert db_session.query(FAQ).filter(FAQ.business_id == b_user.business_id).count() == 1
    # ... and the owner can no longer sign in.
    login = client.post("/api/auth/login", json={"email": v_email, "password": victim["password"]})
    assert login.status_code == 401

    # Consent rows survive, minimised: no direct identifiers left.
    kept = db_session.query(ConsentRecord).filter(ConsentRecord.subject_hash == consent_service.subject_hash(v_email)).all()
    assert {r.type for r in kept} == {"terms", "dpa", "age_confirmation", "marketing_email"}
    assert len([r for r in kept if r.type == "marketing_email"]) == 3  # declined, granted, withdrawn -- history kept
    for r in kept:
        assert r.user_id is None and r.ip_hash is None
        assert r.retain_until == deleted_at + timedelta(days=CONSENT_RETENTION_AFTER_DELETION_DAYS)
        assert r.granted_at is not None and r.source
        assert v_email not in r.subject_hash and len(r.subject_hash) == 64
    identifiers = {v_email.lower(), name.lower(), str(v_uid), str(v_bid), "test owner"}
    for r in kept:
        values = {str(getattr(r, c.name)).lower() for c in ConsentRecord.__table__.columns}
        assert not values & identifiers
    # The hash is reproducible (to match a later dispute) and case-insensitive.
    assert consent_service.subject_hash(v_email.upper()) == kept[0].subject_hash

    # Nightly job just before the 3 years are up: still there. Just after: gone.
    retain = deleted_at + timedelta(days=CONSENT_RETENTION_AFTER_DELETION_DAYS)
    account_service.purge_due(db_session, now=retain - timedelta(days=1))
    assert db_session.query(ConsentRecord).filter(ConsentRecord.subject_hash.isnot(None)).count() == len(kept)
    account_service.purge_due(db_session, now=retain + timedelta(minutes=1))
    assert db_session.query(ConsentRecord).filter(ConsentRecord.subject_hash.isnot(None)).count() == 0
    # The bystander's live consent records are never touched by retention.
    assert db_session.query(ConsentRecord).filter(ConsentRecord.user_id == b_user.id).count() == 4


def test_every_tenant_table_is_covered_by_deletion():
    """Guard: a new table holding tenant data must be reachable from
    businesses, or it would silently survive account deletion."""
    covered = {t.name for t, _, _ in account_service.tenant_tables()}
    for table in Base.metadata.sorted_tables:
        if table.name in account_service._NOT_TENANT_TABLES:
            continue
        refs = {fk.column.table.name for fk in table.foreign_keys}
        if "business_id" in table.c or refs & (covered | {"businesses", "users"}):
            assert table.name in covered, table.name


def test_purge_refuses_to_delete_files_outside_upload_dir(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "upload_dir", str(tmp_path / "uploads"))
    os.makedirs(tmp_path / "uploads")
    outside = tmp_path / "important.txt"
    outside.write_text("keep me")
    account_service._remove_uploaded_file(str(outside))
    assert outside.exists()
