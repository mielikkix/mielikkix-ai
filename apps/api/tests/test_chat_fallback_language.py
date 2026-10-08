"""QA 2026-10-01 (B16): an English question on a business whose primary
fallback text is Norwegian got the Norwegian fallback, because a language
with no fallback_messages entry fell straight back to fallback_message.
chat_service now translates it once and caches it. run_rag and the LLM
provider are mocked."""

from types import SimpleNamespace

import pytest

from app.models.business import BusinessSettings
from app.schemas.chat import ChatMessageRequest
from app.services import chat_service


def _capture_run_rag(seen):
    async def _run(**kwargs):
        seen.append(kwargs["fallback_message"])
        return kwargs["fallback_message"], "faq", 0.0

    return _run


def _settings(db_session, business_id):
    return db_session.query(BusinessSettings).filter(BusinessSettings.business_id == business_id).first()


@pytest.mark.asyncio
async def test_missing_translation_is_translated_once_and_cached(db_session, business, monkeypatch):
    s = _settings(db_session, business["business_id"])
    s.languages = ["no", "en"]
    s.fallback_message = "Jeg har dessverre ikke informasjon om det."
    s.fallback_messages = {}
    db_session.commit()

    calls = []

    async def _translate(text, target_language):
        calls.append(target_language)
        return "Sorry, I don't have information about that."

    monkeypatch.setattr(chat_service, "get_llm_provider", lambda *a: SimpleNamespace(translate=_translate))
    seen = []
    monkeypatch.setattr(chat_service, "run_rag", _capture_run_rag(seen))

    for session in ("s1", "s2"):
        req = ChatMessageRequest(
            business_id=business["business_id"], session_id=session, message="How much is the Business plan per month?"
        )
        resp = await chat_service.handle_message(db_session, req)
        assert resp.lang == "en"

    assert seen == ["Sorry, I don't have information about that."] * 2
    assert calls == ["English"]  # cached after the first message
    assert _settings(db_session, business["business_id"]).fallback_messages["en"].startswith("Sorry")


@pytest.mark.asyncio
async def test_primary_language_uses_base_fallback_without_translating(db_session, business, monkeypatch):
    s = _settings(db_session, business["business_id"])
    s.languages = ["no", "en"]
    s.fallback_message = "Jeg har dessverre ikke informasjon om det."
    db_session.commit()

    def _no_provider(*a):
        raise AssertionError("should not translate")

    monkeypatch.setattr(chat_service, "get_llm_provider", _no_provider)
    seen = []
    monkeypatch.setattr(chat_service, "run_rag", _capture_run_rag(seen))

    req = ChatMessageRequest(business_id=business["business_id"], session_id="s1", message="Hva koster Business-planen?")
    await chat_service.handle_message(db_session, req)

    assert seen == ["Jeg har dessverre ikke informasjon om det."]


def test_opening_settings_fills_missing_translations_once(client, business, db_session, monkeypatch):
    """QA 2026-10-02 (D9): the Norwegian welcome message showed blank though the
    help text says it's auto-filled -- the language predated the feature."""
    from app.api import businesses

    s = _settings(db_session, business["business_id"])
    # German: Norwegian defaults are written in, not machine-translated (QA 2026-10-08).
    s.languages = ["en", "de"]
    s.welcome_messages = {}
    s.fallback_messages = {}
    db_session.commit()

    calls = []

    async def _translate(text, target_language):
        calls.append(target_language)
        return f"[{target_language}] {text}"

    monkeypatch.setattr(businesses, "get_llm_provider", lambda *a: SimpleNamespace(translate=_translate))

    first = client.get("/api/businesses/me/settings", headers=business["headers"]).json()
    second = client.get("/api/businesses/me/settings", headers=business["headers"]).json()

    assert first["welcome_messages"]["de"].startswith("[German]")
    assert first["fallback_messages"]["de"].startswith("[German]")
    assert second["welcome_messages"] == first["welcome_messages"]
    assert calls == ["German", "German"]  # one per text, never repeated
