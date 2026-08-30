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

Multi-provider (added when Groq's own rate-limiting started silently
stalling live voice turns for a minute-plus): every caller still speaks
ONE shape -- OpenAI/Groq's `messages`/`tools` dicts in, `LLMResult` out --
regardless of which provider actually serves the request. Groq and OpenAI
share that shape natively (Groq's SDK is a near-identical clone of
OpenAI's); Anthropic's Messages API has a genuinely different shape
(system prompt as a separate top-level param, tool calls/results as typed
content blocks instead of `tool_calls`/`role: "tool"` messages) -- see
_to_anthropic_messages/_to_anthropic_tool below, which is where that
translation lives, ONCE, so no caller (agents_voice.py, booking_service.py,
support_service.py, seo_service.py, ...) ever has to know which provider
it's actually talking to. Same idiom apps/api/app/rag/providers/__init__.py's
get_llm_provider() factory already uses for the Chat Widget's own (simpler,
non-tool-calling) LLMProvider -- provider selection by a plain string,
defaulting from settings, never hardcoded per call site.

Python note for readers new to async Python: every network call here is
`async def` + `await`, which lets the FastAPI process handle other
requests while waiting on the provider's response instead of blocking the
whole server on one slow call -- the same reason apps/api's own routes
are async.
"""

import asyncio
import json
from dataclasses import dataclass

from .config import get_settings

# Transient errors worth retrying (network hiccup, rate limit, the
# provider's own 5xx) vs. errors that will never succeed on retry (bad API
# key, malformed request) -- retrying those would just waste time and hide
# the real problem. Groq's SDK is an OpenAI-client clone and Anthropic's
# SDK happens to use the exact same names for the equivalent errors, so one
# list covers all three providers; OverloadedError is Anthropic-specific
# (its 529 "temporarily overloaded" signal) but harmless to list here even
# for the other two, since this is just a name match. Imported lazily
# inside the client (see _get_client) so this module doesn't hard-fail at
# import time if a given provider's SDK isn't installed in some consumer
# that only needs the dataclasses below.
_RETRYABLE_EXCEPTION_NAMES = (
    "APIConnectionError",
    "APITimeoutError",
    "RateLimitError",
    "InternalServerError",
    "OverloadedError",
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
    output. Anthropic's own SDK hands back an already-parsed dict (not a
    JSON string) for a tool call's input -- re-serialized to a string here
    (see _to_result_anthropic) so every caller sees the exact same shape
    regardless of provider."""

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


# provider -> (settings field for its API key, settings field for its
# default model) -- resolved lazily in __init__ against get_settings(),
# never at import time, same reasoning apps/api/app/rag/providers/__init__.py's
# get_llm_provider() already follows for the Chat Widget's own provider
# selection.
_PROVIDER_SETTINGS_FIELDS = {
    "groq": ("groq_api_key", "groq_model"),
    "openai": ("openai_api_key", "openai_model"),
    "anthropic": ("anthropic_api_key", "anthropic_model"),
}


class LLMClient:
    def __init__(
        self,
        provider: str | None = None,
        api_key: str | None = None,
        model: str | None = None,
        timeout_seconds: float = 15.0,
        max_retries: int = 2,
    ):
        settings = get_settings()
        self.provider = provider or settings.default_llm_provider
        api_key_field, model_field = _PROVIDER_SETTINGS_FIELDS.get(
            self.provider, _PROVIDER_SETTINGS_FIELDS["groq"]
        )
        self.api_key = api_key or getattr(settings, api_key_field)
        self.model = model or getattr(settings, model_field)
        self.timeout_seconds = timeout_seconds
        self.max_retries = max_retries
        self._client = None

    def _get_client(self):
        if self._client is None:
            # max_retries=0 on every provider's own SDK client, same
            # reasoning across all three: without this, the SDK retries a
            # 429/5xx ITSELF before chat() below ever sees an exception --
            # and does so honoring the provider's own Retry-After header,
            # which under real sustained rate-limiting can be tens of
            # seconds (confirmed live on Groq: 8s, then 20s, then 21s, then
            # 39s, compounding within a SINGLE chat() call). That left a
            # caller (e.g. Voice Receptionist mid-call) silently blocked
            # for up to a minute-plus with no way to react. Disabling each
            # SDK's own retry makes chat()'s loop below the only retry
            # layer -- same retryable-error set, but a fast, bounded
            # 0.5s/1s backoff instead.
            if self.provider == "anthropic":
                from anthropic import AsyncAnthropic

                self._client = AsyncAnthropic(api_key=self.api_key, timeout=self.timeout_seconds, max_retries=0)
            elif self.provider == "openai":
                from openai import AsyncOpenAI

                self._client = AsyncOpenAI(api_key=self.api_key, timeout=self.timeout_seconds, max_retries=0)
            else:
                from groq import AsyncGroq

                self._client = AsyncGroq(api_key=self.api_key, timeout=self.timeout_seconds, max_retries=0)
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
        Your prompt must still ask for JSON in words regardless of
        provider -- Groq/OpenAI's response_format only *enforces* that the
        output parses as JSON, it doesn't invent the schema for you, and
        Anthropic's Messages API has no equivalent enforcement param at all
        (json_mode is a no-op there beyond the prompt itself) -- callers
        that need strict JSON enforcement should prefer Groq/OpenAI for
        that specific call; the existing parse-error/clarification-needed
        fallback every json_mode caller already has remains the real safety
        net either way.

        tools=[{"type": "function", "function": {...}}, ...] gives the model
        real function-calling (OpenAI/Groq's shared shape -- translated to
        Anthropic's own tool-use shape internally when provider="anthropic",
        see _to_anthropic_tool) -- pass tool_choice ("auto"/"required"/
        "none", or a specific-tool dict) to steer whether it's allowed to
        skip calling one. When the model calls a tool, `result.tool_calls`
        is populated and `result.text` may be empty -- the caller executes
        each tool, appends the results as `role: "tool"` messages (this
        client's own OpenAI/Groq-shaped input contract, regardless of
        provider), and calls `chat()` again to continue the conversation.
        """
        client = self._get_client()

        attempt = 0
        while True:
            try:
                if self.provider == "anthropic":
                    response = await self._create_anthropic(client, messages, max_tokens, temperature, tools, tool_choice)
                    return self._to_result_anthropic(response)

                # tools/tool_choice must be OMITTED from the request
                # entirely when unused, not sent as an explicit null --
                # confirmed live (a real groq.BadRequestError: "Only
                # allowed string values for 'tool_choice' are [none, auto,
                # required]") the moment a tools-less call (e.g.
                # agents_booking.py's own json_mode parse call) went
                # through this method after tool_choice was added as an
                # always-forwarded kwarg. Unlike response_format, which
                # Groq/OpenAI accept fine as an explicit null, tool_choice
                # specifically does not -- so build the kwargs conditionally
                # rather than assuming every optional param tolerates the
                # same null-vs-omitted handling.
                extra_kwargs = {}
                if tools is not None:
                    extra_kwargs["tools"] = tools
                if tool_choice is not None:
                    extra_kwargs["tool_choice"] = tool_choice

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

    # --- Anthropic: same public contract, genuinely different wire shape ---

    async def _create_anthropic(self, client, messages, max_tokens, temperature, tools, tool_choice):
        system_text, anthropic_messages = _to_anthropic_messages(messages)
        kwargs = {}
        if tools is not None:
            kwargs["tools"] = [_to_anthropic_tool(t) for t in tools]
        anthropic_tool_choice = _to_anthropic_tool_choice(tool_choice)
        if anthropic_tool_choice is not None:
            kwargs["tool_choice"] = anthropic_tool_choice
        return await client.messages.create(
            model=self.model,
            system=system_text,
            messages=anthropic_messages,
            max_tokens=max_tokens,
            temperature=temperature,
            **kwargs,
        )

    def _to_result_anthropic(self, response) -> LLMResult:
        usage = getattr(response, "usage", None)
        input_tokens = getattr(usage, "input_tokens", 0) or 0
        output_tokens = getattr(usage, "output_tokens", 0) or 0
        llm_usage = (
            LLMUsage(prompt_tokens=input_tokens, completion_tokens=output_tokens, total_tokens=input_tokens + output_tokens)
            if usage
            else None
        )
        text_parts: list[str] = []
        tool_calls: list[ToolCall] = []
        for block in response.content:
            if block.type == "text":
                text_parts.append(block.text)
            elif block.type == "tool_use":
                # block.input is already a parsed dict (Anthropic's SDK
                # decodes it for you) -- re-serialized to a JSON string so
                # ToolCall.arguments has the exact same shape every caller
                # already expects from Groq/OpenAI (see ToolCall's own
                # docstring).
                tool_calls.append(ToolCall(id=block.id, name=block.name, arguments=json.dumps(block.input)))
        return LLMResult(text="".join(text_parts), usage=llm_usage, tool_calls=tool_calls or None)


def _to_anthropic_messages(messages: list[dict]) -> tuple[str, list[dict]]:
    """Translates this client's OpenAI/Groq-shaped `messages` into
    Anthropic's Messages API shape: the system prompt is a separate
    top-level param (not a message with role "system"), and a tool
    call/result isn't a message field (`tool_calls`) or a message role
    ("tool") at all -- both are typed content BLOCKS inside an ordinary
    assistant/user message. Every `role: "tool"` message answering the same
    assistant turn's tool_use blocks must arrive together in ONE user
    message, not as separate consecutive ones (confirmed against
    Anthropic's own API docs) -- consecutive tool results are merged into
    the same trailing user message here rather than appended as new ones.
    """
    system_parts: list[str] = []
    anthropic_messages: list[dict] = []

    for msg in messages:
        role = msg["role"]

        if role == "system":
            system_parts.append(msg["content"])
            continue

        if role == "user":
            anthropic_messages.append({"role": "user", "content": msg["content"]})
            continue

        if role == "assistant":
            tool_calls = msg.get("tool_calls")
            if not tool_calls:
                anthropic_messages.append({"role": "assistant", "content": msg.get("content") or ""})
                continue
            content = []
            if msg.get("content"):
                content.append({"type": "text", "text": msg["content"]})
            for tc in tool_calls:
                content.append(
                    {
                        "type": "tool_use",
                        "id": tc["id"],
                        "name": tc["function"]["name"],
                        "input": json.loads(tc["function"]["arguments"] or "{}"),
                    }
                )
            anthropic_messages.append({"role": "assistant", "content": content})
            continue

        if role == "tool":
            result_block = {"type": "tool_result", "tool_use_id": msg["tool_call_id"], "content": msg["content"]}
            last = anthropic_messages[-1] if anthropic_messages else None
            if (
                last
                and last["role"] == "user"
                and isinstance(last["content"], list)
                and last["content"]
                and last["content"][0].get("type") == "tool_result"
            ):
                last["content"].append(result_block)
            else:
                anthropic_messages.append({"role": "user", "content": [result_block]})
            continue

    return "\n\n".join(system_parts), anthropic_messages


def _to_anthropic_tool(tool: dict) -> dict:
    fn = tool["function"]
    return {
        "name": fn["name"],
        "description": fn.get("description", ""),
        "input_schema": fn.get("parameters") or {"type": "object", "properties": {}},
    }


def _to_anthropic_tool_choice(tool_choice: str | dict | None) -> dict | None:
    if tool_choice is None:
        return None
    if tool_choice == "auto":
        return {"type": "auto"}
    if tool_choice == "required":
        return {"type": "any"}
    if tool_choice == "none":
        # Anthropic has no direct "none" tool_choice -- the caller's own
        # chat() only omits `tools` from the request entirely when it's
        # None, so a genuine "don't use tools" call should pass
        # tools=None rather than tool_choice="none" in the first place.
        # Falling back to "auto" here is a safe default, not a silent
        # behavior change, since none of this codebase's current call
        # sites ever pass tool_choice="none".
        return {"type": "auto"}
    if isinstance(tool_choice, dict):
        name = tool_choice.get("function", {}).get("name")
        if name:
            return {"type": "tool", "name": name}
    return {"type": "auto"}
