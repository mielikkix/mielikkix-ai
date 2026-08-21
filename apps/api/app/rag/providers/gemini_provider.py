from typing import Dict, List, Optional
from .base import LLMProvider, system_prompt, format_history, language_reminder
from ...core.config import settings


class GeminiProvider(LLMProvider):
    def __init__(self, model: str = "gemini-1.5-flash"):
        self.model = model
        self._initialized = False

    def _ensure_init(self):
        if not self._initialized:
            import google.generativeai as genai
            genai.configure(api_key=settings.gemini_api_key)
            self._model = genai.GenerativeModel(self.model)
            self._initialized = True

    async def generate(
        self,
        prompt: str,
        context: str,
        tone: str = "friendly",
        history: Optional[List[Dict[str, str]]] = None,
        languages: Optional[List[str]] = None,
    ) -> str:
        self._ensure_init()
        import asyncio
        full_prompt = (
            f"{system_prompt(tone, languages)}\n\n"
            f"{format_history(history)}"
            f"Context:\n{context}\n\nQuestion: {prompt}\n{language_reminder(languages)}"
        )
        loop = asyncio.get_event_loop()
        response = await loop.run_in_executor(None, self._model.generate_content, full_prompt)
        return response.text

    async def translate(self, text: str, target_language: str) -> str:
        self._ensure_init()
        import asyncio
        prompt = (
            "You are a professional translator. Respond with ONLY the translated text -- "
            f"no quotes, no explanation, no original text.\n\nTranslate the following text "
            f"to {target_language}:\n\n{text}"
        )
        loop = asyncio.get_event_loop()
        response = await loop.run_in_executor(None, self._model.generate_content, prompt)
        return response.text.strip()
