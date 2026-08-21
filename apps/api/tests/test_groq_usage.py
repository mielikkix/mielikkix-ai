"""Unit tests for GroqProvider's token-usage capture (rag/providers/groq_provider.py),
which feeds the platform-admin /api/admin/llm-usage endpoint."""
from types import SimpleNamespace

import pytest

from app.rag.providers.groq_provider import GroqProvider


class _FakeCompletions:
    def __init__(self, response):
        self._response = response

    async def create(self, **kwargs):
        return self._response


def _fake_response(prompt_tokens=10, completion_tokens=5, total_tokens=15, content="hi there"):
    return SimpleNamespace(
        choices=[SimpleNamespace(message=SimpleNamespace(content=content))],
        usage=SimpleNamespace(
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            total_tokens=total_tokens,
        ),
    )


def _stub_client(response):
    return SimpleNamespace(chat=SimpleNamespace(completions=_FakeCompletions(response)))


@pytest.mark.asyncio
async def test_generate_records_last_usage():
    provider = GroqProvider()
    provider._get_client = lambda: _stub_client(_fake_response())
    assert provider.last_usage is None

    reply = await provider.generate("What are your hours?", "We're open 9-5.")
    assert reply == "hi there"
    assert provider.last_usage == {"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15}


@pytest.mark.asyncio
async def test_translate_records_last_usage():
    provider = GroqProvider()
    provider._get_client = lambda: _stub_client(_fake_response(content="Bonjour"))

    reply = await provider.translate("Hello", "French")
    assert reply == "Bonjour"
    assert provider.last_usage == {"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15}


@pytest.mark.asyncio
async def test_generate_without_usage_leaves_last_usage_none():
    provider = GroqProvider()
    response = _fake_response()
    response.usage = None
    provider._get_client = lambda: _stub_client(response)

    await provider.generate("hi", "context")
    assert provider.last_usage is None
