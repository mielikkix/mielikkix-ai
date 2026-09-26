"""Account self-service: data export and account deletion (GDPR Phase 4).

"Account" = the tenant: one Business plus its users and everything scoped to
it. Which tables that covers is derived from the SQLAlchemy metadata
(tenant_tables), not a hand-kept list, so a table added later is exported and
deleted automatically as long as it has a business_id column or a foreign key
to a table that does.
"""
import logging
import os
import uuid
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from typing import Any, Optional

from fastapi import HTTPException
from sqlalchemy import Table, delete, select
from sqlalchemy.orm import Session

from ..core.config import settings
from ..core.database import Base
from ..core.dependencies import is_platform_admin
from ..core.legal import DELETION_GRACE_DAYS
from ..models.article import Article
from ..models.business import Business
from ..models.user import User
from . import consent_service

logger = logging.getLogger(__name__)

# Never tenant data, even though some have a path to users/businesses:
#  - consent_records: minimised and kept for a limited period instead of
#    deleted (consent_service.minimise_for_deleted_user).
#  - articles: the platform's own blog (authors are platform admins only).
#  - bookings / tickets / ticket_messages: Mielikkix's own demo calendar and
#    support desk (see models/booking.py and models/ticket.py).
_NOT_TENANT_TABLES = {"consent_records", "articles", "bookings", "tickets", "ticket_messages", "businesses"}

# Columns never written into an export: credentials, encrypted OAuth tokens,
# vectors. Matched by substring on the column name.
_EXPORT_REDACT = ("password", "token", "secret", "encrypted", "embedding", "api_key")
# Derived search-index text chunks of uploaded documents: large, and the
# documents themselves are listed. Deleted, but not exported.
_EXPORT_SKIP_TABLES = {"document_chunks"}


def tenant_tables() -> list[tuple[Table, str, Optional[Table]]]:
    """(table, column, parent) in dependency order (parents first). column is
    "business_id" for directly scoped tables (parent None), otherwise the FK
    column pointing at an already-scoped parent table."""
    from .. import models  # noqa: F401  make sure every model is registered on Base.metadata

    scoped: dict[str, tuple[Table, str, Optional[Table]]] = {}
    for table in Base.metadata.sorted_tables:
        if table.name in _NOT_TENANT_TABLES:
            continue
        if "business_id" in table.c:
            scoped[table.name] = (table, "business_id", None)
            continue
        for fk in table.foreign_keys:
            if fk.column.table.name in scoped:
                scoped[table.name] = (table, fk.parent.name, fk.column.table)
                break
    return list(scoped.values())


def _predicate(table: Table, column: str, parent: Optional[Table], business_id: uuid.UUID, by_name: dict):
    if parent is None:
        return table.c[column] == business_id
    p_table, p_column, p_parent = by_name[parent.name]
    return table.c[column].in_(select(p_table.c.id).where(_predicate(p_table, p_column, p_parent, business_id, by_name)))


def _jsonable(value: Any) -> Any:
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, (uuid.UUID, Decimal)):
        return str(value)
    if isinstance(value, bytes):
        return None
    return value


def _row_dict(row, columns) -> dict:
    return {c: _jsonable(row[c]) for c in columns if not any(r in c.lower() for r in _EXPORT_REDACT)}


def _consent_dict(r) -> dict:
    return {
        "type": r.type,
        "document_version": r.document_version,
        "granted": r.granted,
        "granted_at": _jsonable(r.granted_at),
        "withdrawn_at": _jsonable(r.withdrawn_at),
        "source": r.source,
    }


def export_data(db: Session, user: User) -> dict:
    """Machine-readable copy of the account's personal data (GDPR art. 15/20).
    Owners get the whole tenant; any other user gets their own profile and
    consent history only."""
    data: dict[str, Any] = {
        "format": "mielikkix-account-export/1",
        "exported_at": datetime.now(timezone.utc).isoformat(),
        "user": {
            "id": str(user.id),
            "email": user.email,
            "full_name": user.full_name,
            "role": user.role,
            "country": user.country,
            "created_at": _jsonable(user.created_at),
        },
        "consent_history": [_consent_dict(r) for r in consent_service.history(db, user.id)],
    }
    if user.role != "owner":
        return data

    business = db.get(Business, user.business_id)
    biz_cols = [c.name for c in Business.__table__.columns]
    data["business"] = _row_dict({c: getattr(business, c) for c in biz_cols}, biz_cols)
    tables = tenant_tables()
    by_name = {t.name: (t, col, parent) for t, col, parent in tables}
    data["tables"] = {}
    for table, column, parent in tables:
        if table.name in _EXPORT_SKIP_TABLES:
            continue
        cols = [c.name for c in table.columns]
        rows = db.execute(select(table).where(_predicate(table, column, parent, business.id, by_name))).mappings()
        data["tables"][table.name] = [_row_dict(r, cols) for r in rows]
    return data


def _require_owner(user: User) -> None:
    if user.role != "owner":
        raise HTTPException(status_code=403, detail="Only the account owner can do this.")


def request_deletion(db: Session, user: User, confirm_name: str, now: Optional[datetime] = None) -> Business:
    _require_owner(user)
    business = db.get(Business, user.business_id)
    if confirm_name.strip() != business.name.strip():
        raise HTTPException(status_code=400, detail="The business name you typed doesn't match.")
    users = db.query(User).filter(User.business_id == business.id).all()
    if any(is_platform_admin(u) for u in users) or db.query(Article).filter(Article.author_id.in_([u.id for u in users])).count():
        raise HTTPException(status_code=400, detail="This is a platform operator account and can't be deleted here.")
    if business.deletion_scheduled_for:
        return business
    now = now or datetime.now(timezone.utc)
    business.deletion_requested_at = now
    business.deletion_scheduled_for = now + timedelta(days=DELETION_GRACE_DAYS)
    db.commit()
    db.refresh(business)
    return business


def cancel_deletion(db: Session, user: User) -> Business:
    _require_owner(user)
    business = db.get(Business, user.business_id)
    business.deletion_requested_at = None
    business.deletion_scheduled_for = None
    db.commit()
    db.refresh(business)
    return business


def _remove_uploaded_file(path: str) -> None:
    """Only ever removes files inside upload_dir, whatever the DB row says."""
    root = os.path.realpath(settings.upload_dir)
    real = os.path.realpath(path)
    try:
        inside = os.path.commonpath([root, real]) == root
    except ValueError:  # different drives on Windows
        inside = False
    if not inside:
        logger.warning("Refusing to delete file outside upload_dir: %s", path)
        return
    try:
        os.remove(real)
    except FileNotFoundError:
        pass
    except OSError:
        logger.exception("Could not delete uploaded file %s", path)


def purge_business(db: Session, business_id: uuid.UUID, now: Optional[datetime] = None) -> list[str]:
    """Hard-deletes a tenant in one transaction. Consent records are minimised
    and kept (not deleted); uploaded files are removed after the commit.
    Returns the deleted users' emails, for the confirmation email."""
    now = now or datetime.now(timezone.utc)
    tables = tenant_tables()
    by_name = {t.name: (t, col, parent) for t, col, parent in tables}

    users = db.query(User).filter(User.business_id == business_id).all()
    emails = [u.email for u in users]
    for u in users:
        consent_service.minimise_for_deleted_user(db, u.id, u.email, now)

    doc_table = by_name.get("documents")
    files = []
    if doc_table:
        t, col, parent = doc_table
        files = [r.file_url for r in db.execute(select(t.c.file_url).where(_predicate(t, col, parent, business_id, by_name)))]

    for table, column, parent in reversed(tables):
        db.execute(delete(table).where(_predicate(table, column, parent, business_id, by_name)))
    db.execute(delete(Business.__table__).where(Business.__table__.c.id == business_id))
    db.commit()

    for path in files:
        _remove_uploaded_file(path)
    return emails


def purge_due(db: Session, now: Optional[datetime] = None) -> list[tuple[str, list[str]]]:
    """Nightly job body: hard-deletes every account past its grace period, then
    drops minimised consent records past their retention. One failing account
    doesn't stop the rest. Returns (business name, emails) per deleted account."""
    now = now or datetime.now(timezone.utc)
    done = []
    due = db.query(Business.id, Business.name).filter(Business.deletion_scheduled_for <= now).all()
    for business_id, name in due:
        try:
            done.append((name, purge_business(db, business_id, now)))
        except Exception:
            db.rollback()
            logger.exception("Account purge failed for business %s", business_id)
    consent_service.purge_expired_minimised_records(db, now)
    return done
