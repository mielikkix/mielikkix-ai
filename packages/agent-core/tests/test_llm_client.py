"""
Per this package's CLAUDE.md testing expectations: unit tests for the LLM
client covering usage extraction and retry/timeout behavior, with the
provider SDK mocked out -- no real Groq call is ever made here.
"""

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from mielikkix_agent_core.llm_client import LLMClient


def _fake_response(text: str, prompt_tokens=10, completion_tokens=5, tool_calls=None):
    return SimpleNamespace(
        choices=[SimpleNamespace(message=SimpleNamespace(content=text, tool_calls=tool_calls))],
        usage=SimpleNamespace(
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            total_tokens=prompt_tokens + completion_tokens,
        ),
    )


def _fake_tool_call(id: str, name: str, arguments: str):
    return SimpleNamespace(id=id, function=SimpleNamespace(name=name, arguments=arguments))


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
    # tools/tool_choice must be OMITTED entirely when unused (Groq rejects
    # an explicit tool_choice=null even with no tools) -- see llm_client.py's
    # own comment on this.
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
async def test_chat_without_tools_omits_tools_and_tool_choice_entirely(monkeypatch):
    """Real live regression: Groq rejects an explicit tool_choice=null with
    a 400 ("Only allowed string values for 'tool_choice' are [none, auto,
    required]") even when tools is also omitted/null -- unlike
    response_format, which Groq accepts fine as an explicit null. A plain
    call (no tools=) must not send either key at all, not send them as
    None."""
    client = LLMClient(api_key="test-key", model="test-model")
    fake_create = AsyncMock(return_value=_fake_response("plain text"))
    monkeypatch.setattr(
        client, "_get_client", lambda: SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=fake_create)))
    )

    await client.chat([{"role": "user", "content": "hi"}])

    sent_kwargs = fake_create.call_args.kwargs
    assert "tools" not in sent_kwargs
    assert "tool_choice" not in sent_kwargs


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


@pytest.mark.asyncio
async def test_chat_with_tools_forwards_tools_and_tool_choice(monkeypatch):
    client = LLMClient(api_key="test-key", model="test-model")
    fake_create = AsyncMock(return_value=_fake_response(""))
    monkeypatch.setattr(
        client, "_get_client", lambda: SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=fake_create)))
    )
    tools = [{"type": "function", "function": {"name": "check_availability"}}]

    await client.chat([{"role": "user", "content": "book me a haircut"}], tools=tools, tool_choice="auto")

    fake_create.assert_awaited_once_with(
        model="test-model",
        messages=[{"role": "user", "content": "book me a haircut"}],
        max_tokens=512,
        temperature=0.7,
        response_format=None,
        tools=tools,
        tool_choice="auto",
    )


@pytest.mark.asyncio
async def test_chat_returns_tool_calls_when_model_requests_one(monkeypatch):
    client = LLMClient(api_key="test-key", model="test-model")
    tool_call = _fake_tool_call("call_1", "check_availability", '{"description": "haircut tomorrow"}')
    fake_create = AsyncMock(return_value=_fake_response("", tool_calls=[tool_call]))
    monkeypatch.setattr(
        client, "_get_client", lambda: SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=fake_create)))
    )

    result = await client.chat([{"role": "user", "content": "book me a haircut"}], tools=[{}])

    assert result.text == ""
    assert result.tool_calls is not None
    assert len(result.tool_calls) == 1
    assert result.tool_calls[0].id == "call_1"
    assert result.tool_calls[0].name == "check_availability"
    assert result.tool_calls[0].arguments == '{"description": "haircut tomorrow"}'


@pytest.mark.asyncio
async def test_chat_tool_calls_is_none_on_a_plain_text_reply(monkeypatch):
    client = LLMClient(api_key="test-key", model="test-model")
    fake_create = AsyncMock(return_value=_fake_response("Sure, what time works?"))
    monkeypatch.setattr(
        client, "_get_client", lambda: SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=fake_create)))
    )

    result = await client.chat([{"role": "user", "content": "hi"}], tools=[{}])

    assert result.text == "Sure, what time works?"
    assert result.tool_calls is None
