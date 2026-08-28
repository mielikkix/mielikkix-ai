"""
The one LLM client every Force agent (and eventually the Chat Widget) calls
through -- generalizes apps/api/app/rag/providers/groq_provider.py's Groq
wrapper so retries/timeouts/usage-tracking live in exactly one place. See
this package's CLAUDE.md, and root CLAUDE.md convention #1: never
reimplement this per agent.

Deliberately lower-level than groq_provider.py: this takes plain OpenAI-
style `messages` (system/user/assistant dicts) and returns raw text --
no RAG-specific prompt template (the "Context:\\n...\\nQuestion:" framing)
baked in, since only the Chat Widget's grounded-Q&A flow needs that shape.
Each agent builds its own messages list and owns its own system prompt.

Python note for readers new to async Python: every network call here is
`async def` + `await`, which lets the FastAPI process handle other
requests while waiting on Groq's response instead of blocking the whole
server on one slow call -- the same reason apps/api's own routes are async.
"""

import asyncio
from dataclasses import dataclass

from .config import get_settings

# Transient errors worth retrying (network hiccup, rate limit, Groq's own
# 5xx) vs. errors that will never succeed on retry (bad API key, malformed
# request) -- retrying those would just waste time and hide the real
# problem. Imported lazily inside the client (see _get_client) so this
# module doesn't hard-fail at import time if `groq` isn't installed yet in
# some consumer that only needs the dataclasses below.
_RETRYABLE_EXCEPTION_NAMES = (
    "APIConnectionError",
    "APITimeoutError",
    "RateLimitError",
    "InternalServerError",
)


@dataclass
class LLMUsage:
    prompt_tokens: int
    completion_tokens: int
    total_tokens: int


@dataclass
class ToolCall:
    """One function the model wants called, from a `chat(tools=...)` reply.
    `arguments` is the raw JSON string the model produced -- untrusted input
    from this app's own perspective (same as any other model completion), so
    the caller does its own `json.loads` and validates the shape, exactly
    like `agents_booking.py`'s `_parse_request` already does for json_mode
    output."""

    id: str
    name: str
    arguments: str


@dataclass
class LLMResult:
    text: str
    usage: LLMUsage | None
    # None for every call that doesn't pass `tools=` -- populated only when
    # the model chose to call one or more tools instead of (or before)
    # replying in prose. `text` is "" on a tool-calls-only turn.
    tool_calls: list[ToolCall] | None = None


class LLMClient:
    def __init__(
        self,
        api_key: str | None = None,
        model: str | None = None,
        timeout_seconds: float = 15.0,
        max_retries: int = 2,
    ):
        settings = get_settings()
        self.api_key = api_key or settings.groq_api_key
        self.model = model or settings.groq_model
        self.timeout_seconds = timeout_seconds
        self.max_retries = max_retries
        self._client = None

    def _get_client(self):
        if self._client is None:
            from groq import AsyncGroq

            self._client = AsyncGroq(api_key=self.api_key, timeout=self.timeout_seconds)
        return self._client

    def _is_retryable(self, exc: Exception) -> bool:
        return type(exc).__name__ in _RETRYABLE_EXCEPTION_NAMES

    async def chat(
        self,
        messages: list[dict],
        *,
        max_tokens: int = 512,
        temperature: float = 0.7,
        json_mode: bool = False,
        tools: list[dict] | None = None,
        tool_choice: str | dict | None = None,
    ) -> LLMResult:
        """Send a chat-completion request. Retries transient failures with
        a short exponential backoff (0.5s, 1s, ...); re-raises immediately
        on anything non-retryable, and re-raises the last error once
        max_retries is exhausted -- callers decide their own fallback
        behavior (e.g. a TwiML apology line) rather than this client
        swallowing the failure silently.

        json_mode=True asks the provider to return a raw JSON object as
        `result.text` (still a `str` -- this doesn't parse it for you,
        `json.loads(result.text)` is still the caller's job) instead of
        free-form prose, e.g. for a classification call that needs
        {"category": ..., "confidence": ...} back rather than a sentence.
        Added for Support Triage's classification step (see
        apps/agents/support-triage/CLAUDE.md) -- shared here, per this
        package's CLAUDE.md convention #1, rather than any one agent
        hand-rolling "please respond in JSON" prompt-wrangling itself. Your
        prompt must still ask for JSON in words (Groq requires this even in
        json_mode) -- this only *enforces* that the output parses as JSON,
        it doesn't invent the schema for you.

        tools=[{"type": "function", "function": {...}}, ...] gives the model
        real function-calling (OpenAI/Groq's shared shape) -- pass tool_choice
        ("auto"/"required"/"none", or a specific-tool dict) to steer whether
        it's allowed to skip calling one. Added for Voice Receptionist's
        booking handoff (see apps/agents/voice-receptionist/CLAUDE.md's Phase
        4) -- shared here rather than per-agent, per this package's own
        convention #1, since any future agent needing real actions (not just
        a reply) needs the same capability. When the model calls a tool,
        `result.tool_calls` is populated and `result.text` may be empty --
        the caller executes each tool, appends the results as `role: "tool"`
        messages, and calls `chat()` again to continue the conversation
        (Groq's own message-shape convention, not something this wrapper
        abstracts away, since the exact tool-result message shape is the
        caller's own conversation loop to manage).
        """
        client = self._get_client()
        # tools/tool_choice must be OMITTED from the request entirely when
        # unused, not sent as an explicit null -- confirmed live (a real
        # groq.BadRequestError: "Only allowed string values for
        # 'tool_choice' are [none, auto, required]") the moment a
        # tools-less call (e.g. agents_booking.py's own json_mode parse
        # call) went through this method after tool_choice was added as an
        # always-forwarded kwarg. Unlike response_format, which Groq
        # accepts fine as an explicit null, tool_choice specifically does
        # not -- so build the kwargs conditionally rather than assuming
        # every optional param tolerates the same null-vs-omitted handling.
        extra_kwargs = {}
        if tools is not None:
            extra_kwargs["tools"] = tools
        if tool_choice is not None:
            extra_kwargs["tool_choice"] = tool_choice

        attempt = 0
        while True:
            try:
                response = await client.chat.completions.create(
                    model=self.model,
                    messages=messages,
                    max_tokens=max_tokens,
                    temperature=temperature,
                    response_format={"type": "json_object"} if json_mode else None,
                    **extra_kwargs,
                )
                return self._to_result(response)
            except Exception as exc:
                if attempt >= self.max_retries or not self._is_retryable(exc):
                    raise
                await asyncio.sleep(0.5 * (2**attempt))
                attempt += 1

    def _to_result(self, response) -> LLMResult:
        usage = getattr(response, "usage", None)
        llm_usage = (
            LLMUsage(
                prompt_tokens=getattr(usage, "prompt_tokens", 0) or 0,
                completion_tokens=getattr(usage, "completion_tokens", 0) or 0,
                total_tokens=getattr(usage, "total_tokens", 0) or 0,
            )
            if usage
            else None
        )
        message = response.choices[0].message
        # Groq (like OpenAI) leaves `content` as None, not "", on a
        # tool-calls-only turn -- normalize so callers can always treat
        # `result.text` as a plain str.
        text = message.content or ""
        raw_tool_calls = getattr(message, "tool_calls", None)
        tool_calls = (
            [
                ToolCall(id=tc.id, name=tc.function.name, arguments=tc.function.arguments)
                for tc in raw_tool_calls
            ]
            if raw_tool_calls
            else None
        )
        return LLMResult(text=text, usage=llm_usage, tool_calls=tool_calls)
