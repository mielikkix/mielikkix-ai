import re

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from sqlalchemy import func
from ..core.database import get_db
from ..core.dependencies import get_current_user, get_current_business
from ..models.user import User
from ..models.business import Business
from ..models.conversation import Conversation, Message
from ..models.lead import Lead
from ..schemas.analytics import AnalyticsSummary, TopQuestion
from ..services import plan_service

router = APIRouter(prefix="/api/analytics", tags=["analytics"])

_WORD_RE = re.compile(r"[\w']+", re.UNICODE)


def top_visitor_questions(rows, limit: int = 5) -> list[tuple[str, int]]:
    """rows: (conversation_id, message). Groups case/punctuation variants, counts
    each conversation once per question, skips messages under 2 words or 6
    letters ("how?", "hi"), and shows the most recent wording of each."""
    seen: dict[str, set] = {}
    shown: dict[str, str] = {}
    for conversation_id, text in rows:
        words = _WORD_RE.findall((text or "").lower())
        if len(words) < 2 or sum(len(w) for w in words) < 6:
            continue
        key = " ".join(words)
        seen.setdefault(key, set()).add(conversation_id)
        shown.setdefault(key, text.strip())
    ranked = sorted(seen.items(), key=lambda kv: len(kv[1]), reverse=True)[:limit]
    return [(shown[key], len(convs)) for key, convs in ranked]


@router.get("/summary", response_model=AnalyticsSummary)
def get_summary(
    current_user: User = Depends(get_current_user),
    business: Business = Depends(get_current_business),
    db: Session = Depends(get_db),
):
    business_id = current_user.business_id
    tier = plan_service.resolve_analytics_tier(business)  # "basic" | "standard" | "advanced"

    real = plan_service.not_test_chat()  # the dashboard's test chats never count
    conv_count = db.query(func.count(Conversation.id)).filter(
        Conversation.business_id == business_id, real
    ).scalar()

    lead_count = db.query(func.count(Lead.id)).filter(
        Lead.business_id == business_id
    ).scalar()

    msg_count = (
        db.query(func.count(Message.id))
        .join(Conversation, Message.conversation_id == Conversation.id)
        .filter(Conversation.business_id == business_id, real, Message.sender == "visitor")
        .scalar()
    )

    # "Basic" (Free plan) only gets the headline counts above -- the
    # question/intent breakdowns are a "standard"/"advanced" perk.
    top_questions: list[TopQuestion] = []
    if tier in ("standard", "advanced"):
        # QA 2026-10-02 (D10): "how?" was the top question (8 times). Each
        # question now counts once per conversation, near-identical wording is
        # grouped, and one-word / very short messages are left out.
        rows = (
            db.query(Message.conversation_id, Message.content)
            .join(Conversation, Message.conversation_id == Conversation.id)
            .filter(Conversation.business_id == business_id, real, Message.sender == "visitor")
            .order_by(Message.created_at.desc())
            .limit(5000)
            .all()
        )
        top_questions = [TopQuestion(question=text, count=n) for text, n in top_visitor_questions(rows)]

    intent_breakdown: dict[str, int] = {}
    if tier == "advanced":
        # Conversations per intent, not messages (QA 2026-10-02, D10: the
        # counts added up to 112 messages while there were 37 conversations).
        intent_rows = (
            db.query(Message.intent, func.count(func.distinct(Message.conversation_id)).label("cnt"))
            .join(Conversation, Message.conversation_id == Conversation.id)
            .filter(
                Conversation.business_id == business_id,
                real,
                Message.sender == "ai",
                Message.intent.isnot(None),
            )
            .group_by(Message.intent)
            .all()
        )
        intent_breakdown = {r.intent: r.cnt for r in intent_rows}

    return AnalyticsSummary(
        conversation_count=conv_count or 0,
        lead_count=lead_count or 0,
        message_count=msg_count or 0,
        analytics_tier=tier,
        top_questions=top_questions,
        intent_breakdown=intent_breakdown,
    )
