"""Consent records (GDPR Phase 3): what a user agreed to at sign-up, and their
marketing-email choice. consent_records is append-only -- see
models/consent_record.py -- so the latest row per (user, type) is the
current state.
"""
import hashlib
import hmac
import uuid
from datetime import datetime, timedelta, timezone
from typing import Optional

from jose import JWTError, jwt
from sqlalchemy.orm import Session

from ..core.config import settings
from ..core.legal import (
    CONSENT_AGE,
    CONSENT_DPA,
    CONSENT_MARKETING,
    CONSENT_RETENTION_AFTER_DELETION_DAYS,
    CONSENT_TERMS,
    DPA_VERSION,
    SOURCE_REACCEPT,
    SOURCE_REGISTER,
    TERMS_VERSION,
)
from ..models.consent_record import ConsentRecord

_UNSUBSCRIBE_PURPOSE = "unsubscribe"


def hash_ip(ip: Optional[str]) -> Optional[str]:
    """Keyed hash, so the stored value can corroborate a record without being
    reversible to the raw address by anyone lacking the server secret."""
    if not ip:
        return None
    return hmac.new(settings.secret_key.encode(), ip.encode(), hashlib.sha256).hexdigest()


def record_registration_consents(
    db: Session, user_id: uuid.UUID, marketing_opt_in: bool, ip_hash: Optional[str]
) -> None:
    """Adds (does not commit) the sign-up rows. Terms/DPA/age are only ever
    recorded as granted here because RegisterRequest rejects anything else."""
    now = datetime.now(timezone.utc)
    rows = [
        (CONSENT_TERMS, TERMS_VERSION, True),
        (CONSENT_DPA, DPA_VERSION, True),
        (CONSENT_AGE, None, True),
        (CONSENT_MARKETING, None, marketing_opt_in),
    ]
    for type_, version, granted in rows:
        db.add(
            ConsentRecord(
                user_id=user_id,
                type=type_,
                document_version=version,
                granted=granted,
                granted_at=now,
                source=SOURCE_REGISTER,
                ip_hash=ip_hash,
            )
        )


def latest(db: Session, user_id: uuid.UUID, type_: str) -> Optional[ConsentRecord]:
    return (
        db.query(ConsentRecord)
        .filter(ConsentRecord.user_id == user_id, ConsentRecord.type == type_)
        .order_by(ConsentRecord.granted_at.desc())
        .first()
    )


def has_marketing_consent(db: Session, user_id: uuid.UUID) -> bool:
    record = latest(db, user_id, CONSENT_MARKETING)
    return bool(record and record.granted and record.withdrawn_at is None)


def set_marketing_consent(db: Session, user_id: uuid.UUID, granted: bool, source: str) -> None:
    """Records a new marketing decision (and commits). No-op if it wouldn't
    change anything, so repeated unsubscribe clicks don't pile up rows."""
    current = latest(db, user_id, CONSENT_MARKETING)
    currently_granted = bool(current and current.granted and current.withdrawn_at is None)
    if currently_granted == granted:
        return
    now = datetime.now(timezone.utc)
    if current and current.granted and not granted:
        current.withdrawn_at = now
    db.add(ConsentRecord(user_id=user_id, type=CONSENT_MARKETING, granted=granted, granted_at=now, source=source))
    db.commit()


def _unsubscribe_key() -> str:
    # Derived key: an unsubscribe token must never be accepted as a session
    # token (get_current_user decodes with settings.secret_key) or vice versa.
    return hmac.new(settings.secret_key.encode(), b"marketing-unsubscribe", hashlib.sha256).hexdigest()


def make_unsubscribe_token(user_id: uuid.UUID) -> str:
    # No expiry on purpose: an unsubscribe link in an old email must still work.
    return jwt.encode({"uid": str(user_id), "purpose": _UNSUBSCRIBE_PURPOSE}, _unsubscribe_key(), algorithm="HS256")


def read_unsubscribe_token(token: str) -> Optional[uuid.UUID]:
    try:
        payload = jwt.decode(token, _unsubscribe_key(), algorithms=["HS256"])
        if payload.get("purpose") != _UNSUBSCRIBE_PURPOSE:
            return None
        return uuid.UUID(payload["uid"])
    except (JWTError, KeyError, ValueError, TypeError):
        return None


def current_versions() -> dict[str, str]:
    """Documents a user must have accepted, at their current versions. A
    function (not a constant) so tests can bump a version via monkeypatch."""
    return {CONSENT_TERMS: TERMS_VERSION, CONSENT_DPA: DPA_VERSION}


def pending_documents(db: Session, user_id: uuid.UUID) -> list[str]:
    """Documents whose CURRENT version this user hasn't accepted -- after a
    version bump, or for accounts created before sign-up consent existed.
    Non-empty means the dashboard shows the re-acceptance modal and
    get_current_user blocks everything except the allow-listed routes."""
    pending = []
    for type_, version in current_versions().items():
        record = latest(db, user_id, type_)
        if not (record and record.granted and record.document_version == version):
            pending.append(type_)
    return pending


def accept_documents(db: Session, user_id: uuid.UUID, documents: list[str], ip_hash: Optional[str]) -> None:
    versions = current_versions()
    now = datetime.now(timezone.utc)
    for type_ in documents:
        db.add(
            ConsentRecord(
                user_id=user_id,
                type=type_,
                document_version=versions[type_],
                granted=True,
                granted_at=now,
                source=SOURCE_REACCEPT,
                ip_hash=ip_hash,
            )
        )
    db.commit()


def history(db: Session, user_id: uuid.UUID) -> list[ConsentRecord]:
    return (
        db.query(ConsentRecord)
        .filter(ConsentRecord.user_id == user_id)
        .order_by(ConsentRecord.granted_at.desc(), ConsentRecord.type)
        .all()
    )


def subject_hash(email: str) -> str:
    """HMAC-SHA256 of the lowercased email with a key derived from the server
    secret -- a plain SHA-256 of an email is reversible by hashing lists of
    known addresses; this is only reproducible by us, when matching a dispute."""
    key = hmac.new(settings.secret_key.encode(), b"consent-subject", hashlib.sha256).digest()
    return hmac.new(key, email.strip().lower().encode(), hashlib.sha256).hexdigest()


def minimise_for_deleted_user(db: Session, user_id: uuid.UUID, email: str, now: datetime) -> None:
    """Called (in the purge transaction) before a user is deleted: keeps each
    consent row as proof of what was agreed, stripped to subject_hash + type,
    version, granted/withdrawn timestamps and source, for
    CONSENT_RETENTION_AFTER_DELETION_DAYS. Covers every type, withdrawals included."""
    db.query(ConsentRecord).filter(ConsentRecord.user_id == user_id).update(
        {
            ConsentRecord.user_id: None,
            ConsentRecord.ip_hash: None,
            ConsentRecord.subject_hash: subject_hash(email),
            ConsentRecord.retain_until: now + timedelta(days=CONSENT_RETENTION_AFTER_DELETION_DAYS),
        },
        synchronize_session=False,
    )


def purge_expired_minimised_records(db: Session, now: datetime) -> int:
    """Nightly: hard-deletes minimised records whose retention has ended."""
    count = (
        db.query(ConsentRecord)
        .filter(ConsentRecord.user_id.is_(None), ConsentRecord.retain_until <= now)
        .delete(synchronize_session=False)
    )
    db.commit()
    return count
