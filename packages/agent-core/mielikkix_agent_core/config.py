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
    # Per-tier model assignment across the Force agents (see root CLAUDE.md
    # and each agent's own _llm_client construction for which tier it's
    # on): Voice Receptionist and "simple" agents default to OpenAI,
    # Booking Assistant and other "complex" agents default to Anthropic
    # Claude Sonnet, with Claude Opus available for a future genuinely
    # "very complex" workflow. Empty api keys are fine at import time --
    # LLMClient only fails if a call actually reaches a provider with no
    # key configured, same as groq_api_key already behaves.
    openai_api_key: str = ""
    openai_model: str = "gpt-4o"
    openai_mini_model: str = "gpt-4o-mini"
    anthropic_api_key: str = ""
    anthropic_model: str = "claude-sonnet-5"
    anthropic_opus_model: str = "claude-opus-5"
    # Only needed for an "identity-linked" API key scoped to more than one
    # workspace (confirmed live: such a key gets a 400 "anthropic-workspace-id
    # is required..." on every request until this is set) -- a plain
    # single-workspace key from Console -> Settings -> API Keys doesn't need
    # this at all. Find it at console.anthropic.com's workspace settings page
    # if you hit that error.
    anthropic_workspace_id: str = ""

    class Config:
        env_file = str(_find_root_env_file())
        extra = "ignore"


@lru_cache()
def get_settings() -> AgentCoreSettings:
    return AgentCoreSettings()
