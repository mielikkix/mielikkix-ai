from typing import Dict, List, Optional
from .base import LLMProvider, system_prompt, language_reminder
from ...core.config import settings


class GroqProvider(LLMProvider):
    def __init__(self, model: str = "llama-3.1-8b-instant"):
        self.model = model
        self._client = None
        # Token usage from the most recent generate()/translate() call, read
        # by rag/pipeline.py and api/businesses.py to log an LLMUsageLog row
        # -- see files/ARCHITECTURE.md's admin dashboard section. None until
        # a call succeeds, or if the SDK response omitted `usage`.
        self.last_usage: dict | None = None

    def _get_client(self):
        if not self._client:
            from groq import AsyncGroq
            self._client = AsyncGroq(api_key=settings.groq_api_key)
        return self._client

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
        client = self._get_client()
        system = system_prompt(tone, languages)
        user_message = f"Context:\n{context}\n\nQuestion: {prompt}\n{language_reminder(languages)}"

        messages = [{"role": "system", "content": system}]
        for turn in history or []:
            role = "user" if turn.get("sender") == "visitor" else "assistant"
            messages.append({"role": role, "content": turn["content"]})
        messages.append({"role": "user", "content": user_message})

        response = await client.chat.completions.create(
            model=self.model,
            messages=messages,
            max_tokens=512,
        )
        self._record_usage(response)
        return response.choices[0].message.content

    async def translate(self, text: str, target_language: str) -> str:
        client = self._get_client()
        response = await client.chat.completions.create(
            model=self.model,
            messages=[
                {"role": "system", "content": "You are a professional translator. Respond with ONLY the translated text -- no quotes, no explanation, no original text."},
                {"role": "user", "content": f"Translate the following text to {target_language}:\n\n{text}"},
            ],
            max_tokens=512,
        )
        self._record_usage(response)
        return response.choices[0].message.content.strip()
