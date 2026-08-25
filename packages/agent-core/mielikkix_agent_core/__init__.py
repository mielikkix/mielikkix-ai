"""mielikkix-agent-core: shared LLM client used by every Mielikkix Force
agent and the Chat Widget. See this package's CLAUDE.md for what belongs
here vs. in an individual agent."""

from .llm_client import LLMClient, LLMResult, LLMUsage

__version__ = "0.1.0"
__all__ = ["LLMClient", "LLMResult", "LLMUsage"]
