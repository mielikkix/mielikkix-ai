from datetime import datetime, timedelta, timezone
from typing import List, Optional
from uuid import UUID
from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query, Request
from sqlalchemy.orm import Session, joinedload
from ..core.database import get_db
from ..core.dependencies import get_current_user, get_current_business
from ..core.limiter import limiter
from ..core.plans import get_plan
from ..models.user import User
from ..models.business import Business
from ..schemas.chat import ChatMessageRequest, ChatMessageResponse, ConversationOut, ConversationStatusUpdate, TestChatRequest
from ..services.chat_service import TEST_CHANNEL, handle_message
from ..services import plan_service
from ..models.conversation import Conversation, Message
from ..models.lead import Lead
from ..services import retention_service
from pydantic import BaseModel

router = APIRouter(prefix="/api/chat", tags=["chat"])


@router.post("/message", response_model=ChatMessageResponse)
@limiter.limit("10/minute")
async def chat_message(
    request: Request, req: ChatMessageRequest, background_tasks: BackgroundTasks, db: Session = Depends(get_db)
):
    return await handle_message(db, req, background_tasks, origin=request.headers.get("origin"))


@router.get("/conversations", response_model=List[ConversationOut])
def list_conversations(
    q: Optional[str] = Query(None, max_length=200),
    status: Optional[str] = Query(None, pattern="^(open|closed)$"),
    current_user: User = Depends(get_current_user),
    business: Business = Depends(get_current_business),
    db: Session = Depends(get_db),
):
    # Conversation history retention is plan-gated (e.g. Free = last 7 days).
    # This only limits what's *shown* here -- nothing is deleted, so
    # upgrading a plan immediately surfaces older history again.
    # Test chats from the dashboard's "Test your chatbot" panel are never listed.
    query = (
        db.query(Conversation)
        .options(joinedload(Conversation.messages))
        .filter(Conversation.business_id == current_user.business_id, plan_service.not_test_chat())
    )
    if status:
        query = query.filter(Conversation.status == status)
    if q and q.strip():
        # Search the transcript (QA 2026-10-02, E3).
        term = f"%{q.strip()}%"
        query = query.filter(
            Conversation.messages.any(Message.content.ilike(term)) | Conversation.session_id.ilike(term)
        )
    history_days = get_plan(business.plan).limits.conversation_history_days
    if history_days is not None:
        cutoff = datetime.now(timezone.utc) - timedelta(days=history_days)
        query = query.filter(Conversation.started_at >= cutoff)
    return query.order_by(Conversation.started_at.desc()).limit(50).all()


@router.patch("/conversations/{conversation_id}", response_model=ConversationOut)
def update_conversation_status(
    conversation_id: str,
    body: ConversationStatusUpdate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Close a conversation the owner has dealt with, or reopen it (QA
    2026-10-02, D10: every conversation stayed "open" forever). The visitor
    writing again reopens it automatically."""
    conv = db.query(Conversation).filter(
        Conversation.id == conversation_id,
        Conversation.business_id == current_user.business_id,
    ).first()
    if not conv:
        raise HTTPException(status_code=404, detail="Conversation not found")
    conv.status = body.status
    conv.ended_at = datetime.now(timezone.utc) if body.status == "closed" else None
    db.commit()
    db.refresh(conv)
    return conv


@router.post("/test", response_model=ChatMessageResponse)
@limiter.limit("20/minute")
async def test_chat(
    request: Request,
    body: TestChatRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """The dashboard's "Test your chatbot" panel (QA 2026-10-02, E5): the same
    answer pipeline the live widget uses, but marked as a test -- it never
    counts toward the plan, the Overview stats or the Conversations list."""
    req = ChatMessageRequest(business_id=str(current_user.business_id), session_id=body.session_id, message=body.message)
    return await handle_message(db, req, channel=TEST_CHANNEL)


@router.delete("/conversations/{conversation_id}")
def delete_conversation(
    conversation_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    conv = db.query(Conversation).filter(
        Conversation.id == conversation_id,
        Conversation.business_id == current_user.business_id,
    ).first()
    if not conv:
        raise HTTPException(status_code=404, detail="Conversation not found")

    # Leads are the valuable record here -- unlink rather than cascade-delete
    # them just because the conversation that produced one is being removed.
    db.query(Lead).filter(Lead.conversation_id == conversation_id).update({"conversation_id": None})
    db.delete(conv)
    db.commit()
    return {"ok": True}


class VisitorEraseRequest(BaseModel):
    email: Optional[str] = None
    phone: Optional[str] = None
    session_id: Optional[str] = None
    lead_id: Optional[UUID] = None


@router.post("/visitors/erase")
def erase_visitor(
    req: VisitorEraseRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """GDPR Phase 5: a business erasing one of ITS visitors' data on that
    visitor's request (Mielikkix is the processor; see DPA "assistance with
    data subject requests"). Deletes the visitor's leads and conversations
    in this business only."""
    if not req.lead_id and not any(v and v.strip() for v in (req.email, req.phone, req.session_id)):
        raise HTTPException(status_code=422, detail="Give a lead, or the visitor's email, phone or chat session ID.")
    return retention_service.erase_visitor(
        db, current_user.business_id, email=req.email, phone=req.phone, session_id=req.session_id, lead_id=req.lead_id
    )


@router.get("/history/{session_id}", response_model=ConversationOut)
def get_history(session_id: str, business_id: str, db: Session = Depends(get_db)):
    conv = db.query(Conversation).filter(
        Conversation.session_id == session_id,
        Conversation.business_id == business_id,
    ).first()
    return conv
