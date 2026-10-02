from datetime import datetime, timezone

from sqlalchemy.orm import Session
from ..models.conversation import Conversation, Message
from ..models.business import Business, BusinessSettings
from ..schemas.chat import ChatMessageRequest, ChatMessageResponse
from ..rag.pipeline import run_rag, log_llm_usage
from ..rag.providers import get_llm_provider
from ..rag.providers.base import LANGUAGE_NAMES
from ..rag.language_detect import detect_message_language
from ..services import agent_access_service, plan_service, website_service
from fastapi import BackgroundTasks, HTTPException
from ..core.plans import get_plan
from ..models.user import User
from ..notifications import notify_quota_warning

HISTORY_LIMIT = 6


async def _fallback_for(db: Session, biz_settings: BusinessSettings | None, lang: str, primary: str) -> str | None:
    """The "no info found" reply in `lang`. fallback_message itself is the
    primary-language version, so any other language without its own entry is
    translated once here and cached on the settings row (committed with the
    rest of this message). Before this, a missing entry fell straight back to
    the primary-language text -- QA 2026-10-01 (B16): an English question on
    a Norwegian-primary business got "Jeg har dessverre ikke informasjon...".
    An entry the owner deliberately left "" still means "use the primary one"."""
    if biz_settings is None:
        return None
    messages = biz_settings.fallback_messages or {}
    if lang in messages:
        return messages[lang] or biz_settings.fallback_message
    if lang == primary or not biz_settings.fallback_message:
        return biz_settings.fallback_message
    try:
        provider = get_llm_provider(biz_settings.llm_provider, biz_settings.llm_model)
        translated = await provider.translate(biz_settings.fallback_message, LANGUAGE_NAMES.get(lang, lang))
        log_llm_usage(db, biz_settings.business_id, biz_settings.llm_provider, provider, kind="translate")
    except Exception:
        # Provider down/no key: the generic default is English, which is still
        # closer for most visitors than a reply in a language they didn't use.
        return None if lang == "en" else biz_settings.fallback_message
    biz_settings.fallback_messages = {**messages, lang: translated}
    return translated


TEST_CHANNEL = "dashboard_test"


async def handle_message(
    db: Session,
    req: ChatMessageRequest,
    background_tasks: BackgroundTasks | None = None,
    origin: str | None = None,
    channel: str = "website_widget",
) -> ChatMessageResponse:
    is_test = channel == TEST_CHANNEL
    business = db.query(Business).filter(
        Business.id == req.business_id, Business.status.in_(["active", "trial"])
    ).first()
    if not business:
        raise HTTPException(status_code=404, detail="Business not found")

    biz_settings = db.query(BusinessSettings).filter(
        BusinessSettings.business_id == req.business_id
    ).first()

    # Any status: a visitor writing again in a conversation the owner closed
    # reopens it rather than starting a new one (which would count toward the
    # monthly limit a second time).
    conversation = db.query(Conversation).filter(
        Conversation.business_id == req.business_id,
        Conversation.session_id == req.session_id,
        Conversation.channel == channel if is_test else plan_service.not_test_chat(),
    ).first()
    if conversation is not None and conversation.status != "open":
        conversation.status = "open"

    quota_warning = None
    if not conversation:
        # Only a brand-new conversation counts against the monthly cap --
        # a session that's already underway is never cut off mid-thread.
        # The owner's own test chats never count.
        if not is_test:
            plan_service.check_conversation_limit(db, business)
        conversation = Conversation(
            business_id=req.business_id,
            session_id=req.session_id,
            visitor_id=req.visitor_id,
            channel=channel,
        )
        db.add(conversation)
        db.flush()
        if not is_test:
            # The site this widget runs on counts toward the plan's websites.
            website_service.register_from_origin(db, business, origin)
        # 80% / 100% quota email, claimed now (committed with this turn below)
        # so two simultaneous conversations can't both send the same warning.
        quota_warning = None if is_test else plan_service.claim_quota_warning(db, business)

    # Fetched before adding the current message below, so it naturally
    # excludes this turn and only contains prior conversation context.
    history_rows = (
        db.query(Message)
        .filter(Message.conversation_id == conversation.id)
        .order_by(Message.created_at.desc())
        .limit(HISTORY_LIMIT)
        .all()
    )
    history_rows.reverse()
    history = [{"sender": m.sender, "content": m.content} for m in history_rows]

    # Explicit timestamps: the question is stamped when it arrives, the reply
    # when it's ready -- never both at the same flush, so they always sort
    # question-then-answer (QA 2026-10-02, D2).
    visitor_msg = Message(
        conversation_id=conversation.id,
        sender="visitor",
        content=req.message,
        created_at=datetime.now(timezone.utc),
    )
    db.add(visitor_msg)

    provider = biz_settings.llm_provider if biz_settings else "groq"
    model = biz_settings.llm_model if biz_settings else None
    tone = biz_settings.tone if biz_settings else "friendly"
    languages = (biz_settings.languages if biz_settings else None) or ["en"]

    # The visitor's own message decides the reply language -- not their browser's
    # locale, which has no relationship to what they're actually typing (a visitor
    # can easily have Norwegian as a browser default and still type in English).
    # detected_lang goes first in the list passed to the LLM as the tie-breaker
    # for a message that isn't clearly in any supported language, and is used
    # directly to pick the fallback_messages translation below, since that reply
    # never reaches the LLM to detect anything from.
    detected_lang = detect_message_language(req.message, languages, default=languages[0])
    effective_languages = [detected_lang] + [lang for lang in languages if lang != detected_lang]
    resolved_fallback = await _fallback_for(db, biz_settings, detected_lang, languages[0])
    conversation.language = detected_lang

    reply, intent, confidence = await run_rag(
        db=db,
        business_id=str(req.business_id),
        message=req.message,
        llm_provider=provider,
        llm_model=model,
        fallback_message=resolved_fallback,
        tone=tone,
        history=history,
        languages=effective_languages,
    )

    ai_msg = Message(
        conversation_id=conversation.id,
        sender="ai",
        content=reply,
        created_at=datetime.now(timezone.utc),
        intent=intent,
        confidence=confidence,
    )
    db.add(ai_msg)
    db.commit()

    if quota_warning and background_tasks is not None:
        level, used, limit = quota_warning
        owners = [
            u.email for u in db.query(User).filter(User.business_id == business.id, User.role == "owner").all() if u.email
        ]
        if owners:
            background_tasks.add_task(
                notify_quota_warning, owners, business.name, get_plan(business.plan).name, level, used, limit
            )

    # An ungated business's chatbot never offers booking in the first place
    # -- not just blocked after the fact by agents_booking.py's own
    # agent_access_service.require_agent_access check on /request and /confirm.
    suggest_booking = intent == "booking" and agent_access_service.has_agent_access(db, business.id, "booking_assistant")
    # A booking intent almost always also has low confidence (a brand-new
    # business has no FAQ/document actually about booking), which alone
    # would also trigger the lead-capture form below -- confirmed live: a
    # visitor typing "book the meeting" got BOTH a lead form AND a booking
    # panel stacked on top of each other, and only noticed the booking one
    # after scrolling. Once we're already offering the real booking flow,
    # the lead form for that same message is redundant, not additive.
    suggest_lead = not suggest_booking and (intent == "lead" or confidence < 0.3)

    return ChatMessageResponse(
        reply=reply,
        intent=intent,
        confidence=confidence,
        session_id=req.session_id,
        suggest_lead_capture=suggest_lead,
        suggest_booking_flow=suggest_booking,
        lang=detected_lang,
    )
