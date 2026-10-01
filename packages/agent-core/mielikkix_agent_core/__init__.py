"""mielikkix-agent-core: shared LLM client used by every Mielikkix Force
agent and the Chat Widget. See this package's CLAUDE.md for what belongs
here vs. in an individual agent."""

from .guardrails import AI_SAFETY_RULES
from .llm_client import LLMClient, LLMResult, LLMUsage, ToolCall, extract_json_object

__version__ = "0.1.1"
__all__ = ["AI_SAFETY_RULES", "LLMClient", "LLMResult", "LLMUsage", "ToolCall", "extract_json_object"]
