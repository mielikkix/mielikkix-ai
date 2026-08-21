from .base import LLMProvider, EmbeddingProvider
from .groq_provider import GroqProvider
from .gemini_provider import GeminiProvider
from .ollama_provider import OllamaProvider
from ...core.config import settings


def get_llm_provider(provider: str = None, model: str = None) -> LLMProvider:
    provider = provider or settings.default_llm_provider
    if provider == "groq":
        return GroqProvider(model=model or "llama-3.1-8b-instant")
    if provider == "gemini":
        return GeminiProvider(model=model or "gemini-1.5-flash")
    if provider == "ollama":
        return OllamaProvider(model=model or "llama3")
    return GroqProvider()
