from .base import LLMProvider, EmbeddingProvider
from .groq_provider import GroqProvider
from .gemini_provider import GeminiProvider
from .ollama_provider import OllamaProvider
from ...core.config import settings


def get_llm_provider(provider: str = None, model: str = None) -> LLMProvider:
    """`model` is the tenant's own business_settings.llm_model when set;
    otherwise fall back to the env-configured default for that provider
    (settings.*_model) rather than a hardcoded model name -- see the comment
    on Settings.groq_model for why that default has to stay changeable."""
    provider = provider or settings.default_llm_provider
    if provider == "groq":
        return GroqProvider(model=model or settings.groq_model)
    if provider == "gemini":
        return GeminiProvider(model=model or settings.gemini_model)
    if provider == "ollama":
        return OllamaProvider(model=model or settings.ollama_model)
    return GroqProvider(model=settings.groq_model)
