"""
Per this package's CLAUDE.md testing expectations: unit tests for the LLM
client covering usage extraction and retry/timeout behavior, with the
provider SDK mocked out -- no real Groq call is ever made here.
"""

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from mielikkix_agent_core.llm_client import LLMClient


def _fake_response(text: str, prompt_tokens=10, completion_tokens=5):
    return SimpleNamespace(
        choices=[SimpleNamespace(message=SimpleNamespace(content=text))],
        usage=SimpleNamespace(
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            total_tokens=prompt_tokens + completion_tokens,
        ),
    )


@pytest.mark.asyncio
async def test_chat_returns_text_and_usage(monkeypatch):
    client = LLMClient(api_key="test-key", model="test-model")
    fake_create = AsyncMock(return_value=_fake_response("Hello there"))
    monkeypatch.setattr(
        client, "_get_client", lambda: SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=fake_create)))
    )

    result = await client.chat([{"role": "user", "content": "hi"}])

    assert result.text == "Hello there"
    assert result.usage.prompt_tokens == 10
    assert result.usage.completion_tokens == 5
    assert result.usage.total_tokens == 15
    fake_create.assert_awaited_once()


@pytest.mark.asyncio
async def test_chat_json_mode_sets_response_format(monkeypatch):
    client = LLMClient(api_key="test-key", model="test-model")
    fake_create = AsyncMock(return_value=_fake_response('{"category": "billing"}'))
    monkeypatch.setattr(
        client, "_get_client", lambda: SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=fake_create)))
    )

    result = await client.chat([{"role": "user", "content": "hi"}], json_mode=True)

    assert result.text == '{"category": "billing"}'
    fake_create.assert_awaited_once_with(
        model="test-model",
        messages=[{"role": "user", "content": "hi"}],
        max_tokens=512,
        temperature=0.7,
        response_format={"type": "json_object"},
    )


@pytest.mark.asyncio
async def test_chat_without_json_mode_sends_no_response_format(monkeypatch):
    client = LLMClient(api_key="test-key", model="test-model")
    fake_create = AsyncMock(return_value=_fake_response("plain text"))
    monkeypatch.setattr(
        client, "_get_client", lambda: SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=fake_create)))
    )

    await client.chat([{"role": "user", "content": "hi"}])

    assert fake_create.call_args.kwargs["response_format"] is None


@pytest.mark.asyncio
async def test_chat_retries_on_retryable_error_then_succeeds(monkeypatch):
    class RateLimitError(Exception):
        pass

    client = LLMClient(api_key="test-key", model="test-model", max_retries=2)
    fake_create = AsyncMock(side_effect=[RateLimitError("slow down"), _fake_response("ok now")])
    monkeypatch.setattr(
        client, "_get_client", lambda: SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=fake_create)))
    )
    monkeypatch.setattr("mielikkix_agent_core.llm_client.asyncio.sleep", AsyncMock())

    result = await client.chat([{"role": "user", "content": "hi"}])

    assert result.text == "ok now"
    assert fake_create.await_count == 2


@pytest.mark.asyncio
async def test_chat_does_not_retry_non_retryable_error(monkeypatch):
    class AuthenticationError(Exception):
        pass

    client = LLMClient(api_key="bad-key", model="test-model", max_retries=2)
    fake_create = AsyncMock(side_effect=AuthenticationError("invalid api key"))
    monkeypatch.setattr(
        client, "_get_client", lambda: SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=fake_create)))
    )

    with pytest.raises(AuthenticationError):
        await client.chat([{"role": "user", "content": "hi"}])

    fake_create.assert_awaited_once()


@pytest.mark.asyncio
async def test_chat_raises_after_exhausting_retries(monkeypatch):
    class APITimeoutError(Exception):
        pass

    client = LLMClient(api_key="test-key", model="test-model", max_retries=2)
    fake_create = AsyncMock(side_effect=APITimeoutError("timed out"))
    monkeypatch.setattr(
        client, "_get_client", lambda: SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=fake_create)))
    )
    monkeypatch.setattr("mielikkix_agent_core.llm_client.asyncio.sleep", AsyncMock())

    with pytest.raises(APITimeoutError):
        await client.chat([{"role": "user", "content": "hi"}])

    assert fake_create.await_count == 3
