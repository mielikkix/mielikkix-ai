"""QA reports 2026-10-08 (dashboard A-xx, website W-xx). LLM calls and
embeddings are always mocked here."""

from types import SimpleNamespace

import pytest

from app.api import businesses
from app.models.business import BusinessSettings
from app.rag import pipeline
from app.schemas.chat import ChatMessageRequest
from app.services import chat_service
from app.services.chat_defaults import DEFAULT_FALLBACK_MESSAGE, LEAD_PROMPTS


def _settings(db_session, business_id):
    return db_session.query(BusinessSettings).filter(BusinessSettings.business_id == business_id).first()


def _no_matches(monkeypatch):
    monkeypatch.setattr(pipeline, "embed_query", lambda text: [1.0])
    for name in ("retrieve_chunks", "retrieve_faqs", "retrieve_products"):
        monkeypatch.setattr(pipeline, name, lambda *a, **k: [])


def _llm_must_not_be_called(monkeypatch):
    def _fail(*a, **k):
        raise AssertionError("no LLM call expected")

    monkeypatch.setattr(pipeline, "get_llm_provider", _fail)
    monkeypatch.setattr(chat_service, "get_llm_provider", _fail)
    monkeypatch.setattr(businesses, "get_llm_provider", _fail)


# --- W-06: buying intent gets a lead prompt, not "I'm not sure" ---------------


@pytest.mark.asyncio
async def test_buying_question_without_an_answer_invites_the_lead_form(monkeypatch):
    _no_matches(monkeypatch)
    _llm_must_not_be_called(monkeypatch)

    reply, intent, confidence = await pipeline.run_rag(
        db=None,
        business_id="b",
        message="Jeg vil kjøpe Business-planen, kan dere kontakte meg?",
        fallback_message="Det er jeg ikke sikker på. Vil du snakke med teamet vårt?",
        lead_reply=LEAD_PROMPTS["no"],
    )

    assert intent == "lead"
    assert reply == LEAD_PROMPTS["no"]
    assert "ikke sikker" not in reply


@pytest.mark.asyncio
async def test_other_unanswered_questions_still_get_the_fallback(monkeypatch):
    _no_matches(monkeypatch)
    _llm_must_not_be_called(monkeypatch)

    reply, intent, _ = await pipeline.run_rag(
        db=None,
        business_id="b",
        message="What is the airspeed of a swallow?",
        fallback_message="Not sure.",
        lead_reply=LEAD_PROMPTS["en"],
    )

    assert intent == "faq"
    assert reply == "Not sure."


@pytest.mark.asyncio
async def test_chat_reply_to_a_norwegian_buyer_is_the_norwegian_lead_prompt(db_session, business, monkeypatch):
    s = _settings(db_session, business["business_id"])
    s.languages = ["en", "no"]
    s.contact_email = None
    s.contact_phone = None
    db_session.commit()
    _no_matches(monkeypatch)
    _llm_must_not_be_called(monkeypatch)

    resp = await chat_service.handle_message(
        db_session,
        ChatMessageRequest(
            business_id=business["business_id"],
            session_id="w06",
            message="Jeg vil kjøpe Business-planen, kan dere kontakte meg?",
            page_lang="nb",
        ),
    )

    assert resp.lang == "no"
    assert resp.reply == LEAD_PROMPTS["no"]
    assert resp.suggest_lead_capture is True


def test_every_supported_language_has_a_lead_prompt():
    from app.rag.providers.base import LANGUAGE_NAMES

    assert set(LANGUAGE_NAMES) <= set(LEAD_PROMPTS)


# --- W-06: "Vil du tale med vår team?" ----------------------------------------


@pytest.mark.asyncio
async def test_default_fallback_uses_the_written_norwegian_not_a_machine_translation(db_session, business, monkeypatch):
    s = _settings(db_session, business["business_id"])
    s.fallback_message = DEFAULT_FALLBACK_MESSAGE
    s.fallback_messages = {}
    db_session.commit()
    _llm_must_not_be_called(monkeypatch)

    text = await chat_service._fallback_for(db_session, s, "no", "en")

    assert text == "Det er jeg ikke sikker på. Vil du snakke med teamet vårt?"
    assert s.fallback_messages["no"] == text


@pytest.mark.asyncio
async def test_an_owner_written_norwegian_fallback_is_kept(db_session, business, monkeypatch):
    s = _settings(db_session, business["business_id"])
    s.fallback_message = DEFAULT_FALLBACK_MESSAGE
    s.fallback_messages = {"no": "Ring oss gjerne!"}
    db_session.commit()
    _llm_must_not_be_called(monkeypatch)

    assert await chat_service._fallback_for(db_session, s, "no", "en") == "Ring oss gjerne!"


@pytest.mark.asyncio
async def test_enabling_norwegian_fills_the_default_texts_without_an_llm(db_session, business, monkeypatch):
    s = _settings(db_session, business["business_id"])
    s.languages = ["en", "no"]
    s.fallback_message = None
    s.welcome_message = None
    s.fallback_messages = {}
    s.welcome_messages = {}
    db_session.commit()
    _llm_must_not_be_called(monkeypatch)

    await businesses._fill_missing_translations(db_session, s)

    assert s.fallback_messages["no"] == "Det er jeg ikke sikker på. Vil du snakke med teamet vårt?"
    assert s.welcome_messages["no"] == "Hei! Hva kan jeg hjelpe deg med i dag?"


@pytest.mark.asyncio
async def test_a_custom_fallback_is_still_machine_translated(db_session, business, monkeypatch):
    s = _settings(db_session, business["business_id"])
    s.languages = ["en", "no"]
    s.fallback_message = "We'll get back to you soon."
    s.welcome_message = "Welcome!"
    s.fallback_messages = {}
    s.welcome_messages = {}
    db_session.commit()

    async def _translate(text, language):
        return f"[{language}] {text}"

    monkeypatch.setattr(
        businesses, "get_llm_provider", lambda *a: SimpleNamespace(translate=_translate, last_usage=None)
    )

    await businesses._fill_missing_translations(db_session, s)

    assert s.fallback_messages["no"] == "[Norwegian] We'll get back to you soon."
    assert s.welcome_messages["no"] == "[Norwegian] Welcome!"
