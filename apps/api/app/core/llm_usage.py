"""Records token usage for every packages/agent-core LLMClient call (Claude,
OpenAI) into llm_usage_logs, for the platform-admin "AI Usage" page.

The Chat Widget's own Groq provider (rag/providers/) already logs through
rag/pipeline.py's log_llm_usage; this covers the Force agents, which call
LLMClient directly and previously recorded nothing.

Which business a call belongs to: a per-request holder (request_usage_scope,
installed by UsageContextMiddleware) that get_current_user fills in. A holder
object, not a plain ContextVar value, because FastAPI runs sync dependencies in
a worker thread with a COPY of the context -- a value set there never reaches
the async route, but a mutation of the shared holder object does. Public demo
routes have no logged-in business, so their rows have business_id NULL and
show as "Platform / public demos".
"""

import logging
from contextlib import contextmanager
from contextvars import ContextVar

from mielikkix_agent_core import UsageEvent, set_usage_hook

from .database import SessionLocal

logger = logging.getLogger(__name__)

_usage_scope: ContextVar[dict | None] = ContextVar("llm_usage_scope", default=None)

# Swapped in tests (the test DB isn't SessionLocal's database).
session_factory = SessionLocal


def set_usage_business(business_id) -> None:
    """Attributes LLM calls made later in this request to `business_id`."""
    scope = _usage_scope.get()
    if scope is not None:
        scope["business_id"] = business_id


@contextmanager
def usage_business(business_id):
    """For work outside a request (scheduled jobs): attributes LLM calls in the block to `business_id`."""
    token = _usage_scope.set({"business_id": business_id})
    try:
        yield
    finally:
        _usage_scope.reset(token)


class UsageContextMiddleware:
    """Pure ASGI (not BaseHTTPMiddleware), so the holder set here is the one the
    route, its dependencies and its background tasks all see."""

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            return await self.app(scope, receive, send)
        token = _usage_scope.set({})
        try:
            await self.app(scope, receive, send)
        finally:
            _usage_scope.reset(token)


def record_usage(event: UsageEvent) -> None:
    from ..models.llm_usage import LLMUsageLog

    scope = _usage_scope.get() or {}
    db = session_factory()
    try:
        db.add(
            LLMUsageLog(
                business_id=scope.get("business_id"),
                provider=event.provider,
                model=event.model,
                kind=event.tag or "other",
                prompt_tokens=event.usage.prompt_tokens,
                completion_tokens=event.usage.completion_tokens,
                total_tokens=event.usage.total_tokens,
            )
        )
        db.commit()
    finally:
        db.close()


def install() -> None:
    set_usage_hook(record_usage)
