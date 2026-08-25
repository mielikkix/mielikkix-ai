"""
Settings for agent-core itself (just enough to reach an LLM provider).
Deliberately does NOT import apps/api/app/core/config.py -- agent-core is a
shared package consumed by apps/api *and* every apps/agents/* package, so
the dependency direction only ever goes one way (consumers depend on
agent-core, never the reverse). Any agent running standalone (outside
apps/api) still needs this to work on its own.
"""

from pathlib import Path
from functools import lru_cache
from pydantic_settings import BaseSettings


def _find_root_env_file() -> Path:
    # Same walk-up-from-this-file trick as apps/api/app/core/config.py, so
    # this resolves correctly whether the importing process was started
    # from the repo root, from an individual app's own directory, or from
    # inside a Docker image where this package was installed some other way.
    here = Path(__file__).resolve()
    for parent in here.parents:
        candidate = parent / ".env"
        if candidate.is_file():
            return candidate
    return here.parents[-1] / ".env"


class AgentCoreSettings(BaseSettings):
    default_llm_provider: str = "groq"
    groq_api_key: str = ""
    groq_model: str = "openai/gpt-oss-120b"

    class Config:
        env_file = str(_find_root_env_file())
        extra = "ignore"


@lru_cache()
def get_settings() -> AgentCoreSettings:
    return AgentCoreSettings()
