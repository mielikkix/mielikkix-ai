import asyncio
from typing import Dict, List, Optional
from .base import LLMProvider, system_prompt, language_reminder, context_block
from ...core.config import settings

# QA 2026-10-02 (D6): widget replies took 30-40s while Groq itself answers in
# ~1s. The SDK's own retry (max_retries=2) silently waits out Groq's
# Retry-After on a 429, compounding to tens of seconds -- the same stall
# packages/agent-core's LLMClient already disables. So: no hidden SDK retries,
# a bounded timeout, and one quick retry of our own.
_TIMEOUT_SECONDS = 15.0
_RETRYABLE = ("APIConnectionError", "APITimeoutError", "RateLimitError", "InternalServerError")


class GroqProvider(LLMProvider):
    def __init__(self, model: str | None = None):
        # Resolved at call time, not as a default-arg literal, so the model
        # stays env-configurable (see Settings.groq_model).
        self.model = model or settings.groq_model
        self._client = None
        # Token usage from the most recent generate()/translate() call, read
        # by rag/pipeline.py and api/businesses.py to log an LLMUsageLog row
        # -- see files/ARCHITECTURE.md's admin dashboard section. None until
        # a call succeeds, or if the SDK response omitted `usage`.
        self.last_usage: dict | None = None

    def _get_client(self):
        if not self._client:
            from groq import AsyncGroq
            self._client = AsyncGroq(api_key=settings.groq_api_key, timeout=_TIMEOUT_SECONDS, max_retries=0)
        return self._client

    async def _create(self, **kwargs):
        try:
            return await self._get_client().chat.completions.create(**kwargs)
        except Exception as exc:
            if type(exc).__name__ not in _RETRYABLE:
                raise
            await asyncio.sleep(0.5)
            return await self._get_client().chat.completions.create(**kwargs)

    def _record_usage(self, response) -> None:
        usage = getattr(response, "usage", None)
        if not usage:
            self.last_usage = None
            return
        self.last_usage = {
            "prompt_tokens": getattr(usage, "prompt_tokens", 0) or 0,
            "completion_tokens": getattr(usage, "completion_tokens", 0) or 0,
            "total_tokens": getattr(usage, "total_tokens", 0) or 0,
        }

    async def generate(
        self,
        prompt: str,
        context: str,
        tone: str = "friendly",
        history: Optional[List[Dict[str, str]]] = None,
        languages: Optional[List[str]] = None,
    ) -> str:
        system = system_prompt(tone, languages)
        user_message = f"{context_block(context)}\n\nQuestion: {prompt}\n{language_reminder(languages)}"

        messages = [{"role": "system", "content": system}]
        for turn in history or []:
            role = "user" if turn.get("sender") == "visitor" else "assistant"
            messages.append({"role": role, "content": turn["content"]})
        messages.append({"role": "user", "content": user_message})

        response = await self._create(
            model=self.model,
            messages=messages,
            max_tokens=512,
        )
        self._record_usage(response)
        return response.choices[0].message.content

    async def translate(self, text: str, target_language: str) -> str:
        response = await self._create(
            model=self.model,
            messages=[
                {"role": "system", "content": "You are a professional translator. Respond with ONLY the translated text -- no quotes, no explanation, no original text."},
                {"role": "user", "content": f"Translate the following text to {target_language}:\n\n{text}"},
            ],
            max_tokens=512,
        )
        self._record_usage(response)
        return response.choices[0].message.content.strip()
