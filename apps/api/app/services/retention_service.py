"""End-user data retention and erasure for customers' chat widgets (GDPR
Phase 5). Mielikkix is the processor here: the business decides how long its
visitors' conversations are kept (business_settings.conversation_retention_days,
bounded by core/legal.py) and asks us to erase a specific visitor when that
visitor exercises their rights with the business.

Leads are the business's own customer records: retention unlinks them from
an expired conversation rather than deleting them (same as the dashboard's
single-conversation delete). An explicit visitor erasure deletes both.
"""
import re
import uuid
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import func, literal, or_, select
from sqlalchemy.orm import Session

from ..core.legal import CONVERSATION_RETENTION_DEFAULT_DAYS
from ..models.business import BusinessSettings
from ..models.conversation import Conversation, Message
from ..models.lead import Lead


def _delete_conversations(db: Session, ids: list[uuid.UUID]) -> int:
    if not ids:
        return 0
    db.query(Lead).filter(Lead.conversation_id.in_(ids)).update({Lead.conversation_id: None}, synchronize_session=False)
    db.query(Message).filter(Message.conversation_id.in_(ids)).delete(synchronize_session=False)
    return db.query(Conversation).filter(Conversation.id.in_(ids)).delete(synchronize_session=False)


def purge_expired_conversations(db: Session, now: Optional[datetime] = None) -> int:
    """Nightly: per business, deletes conversations whose LAST activity (latest
    message, or start if none) is older than its retention setting. Returns
    how many conversations were deleted in total."""
    now = now or datetime.now(timezone.utc)
    last_message = (
        select(Message.conversation_id, func.max(Message.created_at).label("last_at"))
        .group_by(Message.conversation_id)
        .subquery()
    )
    last_activity = func.coalesce(last_message.c.last_at, Conversation.started_at)
    retention = func.coalesce(BusinessSettings.conversation_retention_days, CONVERSATION_RETENTION_DEFAULT_DAYS)

    expired = db.execute(
        select(Conversation.id)
        .outerjoin(last_message, last_message.c.conversation_id == Conversation.id)
        .outerjoin(BusinessSettings, BusinessSettings.business_id == Conversation.business_id)
        .where(last_activity < literal(now) - func.make_interval(0, 0, 0, retention))
    ).scalars().all()
    deleted = _delete_conversations(db, list(expired))
    db.commit()
    return deleted


def _digits(phone: str) -> str:
    return re.sub(r"\D", "", phone)


def erase_visitor(
    db: Session,
    business_id: uuid.UUID,
    email: Optional[str] = None,
    phone: Optional[str] = None,
    session_id: Optional[str] = None,
    lead_id: Optional[uuid.UUID] = None,
) -> dict:
    """Deletes one visitor's data from ONE business: the given lead, leads matching the email
    (case-insensitive) or phone (digits only), every conversation linked to
    those leads, and every conversation with the given widget session id.
    Strictly scoped to business_id."""
    lead_filters = []
    if lead_id:
        lead = db.query(Lead).filter(Lead.id == lead_id, Lead.business_id == business_id).first()
        if lead is None:
            return {"leads_deleted": 0, "conversations_deleted": 0}
        lead_filters.append(Lead.id == lead.id)
        # The same person's other leads/conversations, found via the lead's own details.
        email = email or lead.email
        phone = phone or lead.phone
    if email:
        lead_filters.append(func.lower(Lead.email) == email.strip().lower())
    if phone and _digits(phone):
        lead_filters.append(func.regexp_replace(Lead.phone, r"\D", "", "g") == _digits(phone))
    leads = (
        db.query(Lead).filter(Lead.business_id == business_id, or_(*lead_filters)).all() if lead_filters else []
    )

    conv_ids = {l.conversation_id for l in leads if l.conversation_id}
    if session_id:
        conv_ids |= set(
            db.execute(
                select(Conversation.id).where(Conversation.business_id == business_id, Conversation.session_id == session_id)
            ).scalars()
        )
    for lead in leads:
        db.delete(lead)
    db.flush()
    conversations = _delete_conversations(db, list(conv_ids))
    db.commit()
    return {"leads_deleted": len(leads), "conversations_deleted": conversations}
