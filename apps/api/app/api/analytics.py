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


@router.get("/summary", response_model=AnalyticsSummary)
def get_summary(
    current_user: User = Depends(get_current_user),
    business: Business = Depends(get_current_business),
    db: Session = Depends(get_db),
):
    business_id = current_user.business_id
    tier = plan_service.resolve_analytics_tier(business)  # "basic" | "standard" | "advanced"

    conv_count = db.query(func.count(Conversation.id)).filter(
        Conversation.business_id == business_id
    ).scalar()

    lead_count = db.query(func.count(Lead.id)).filter(
        Lead.business_id == business_id
    ).scalar()

    msg_count = (
        db.query(func.count(Message.id))
        .join(Conversation, Message.conversation_id == Conversation.id)
        .filter(Conversation.business_id == business_id, Message.sender == "visitor")
        .scalar()
    )

    # "Basic" (Free plan) only gets the headline counts above -- the
    # question/intent breakdowns are a "standard"/"advanced" perk.
    top_questions: list[TopQuestion] = []
    if tier in ("standard", "advanced"):
        top_rows = (
            db.query(Message.content, func.count(Message.id).label("cnt"))
            .join(Conversation, Message.conversation_id == Conversation.id)
            .filter(Conversation.business_id == business_id, Message.sender == "visitor")
            .group_by(Message.content)
            .order_by(func.count(Message.id).desc())
            .limit(5)
            .all()
        )
        top_questions = [TopQuestion(question=r.content, count=r.cnt) for r in top_rows]

    intent_breakdown: dict[str, int] = {}
    if tier == "advanced":
        intent_rows = (
            db.query(Message.intent, func.count(Message.id).label("cnt"))
            .join(Conversation, Message.conversation_id == Conversation.id)
            .filter(
                Conversation.business_id == business_id,
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
