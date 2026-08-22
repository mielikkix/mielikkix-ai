from starlette.types import ASGIApp, Receive, Scope, Send
from starlette.responses import Response

# Public, widget-facing routes are embedded on arbitrary third-party business
# websites we can't know in advance, so they accept any origin. They carry no
# cookies/credentials (the widget uses no auth), so an open origin policy here
# doesn't expose anything sensitive — business_id scoping and rate limiting are
# the real security boundary, not CORS. Everything else keeps the restrictive,
# settings-driven allowlist (see CORSMiddleware in main.py) for the
# authenticated dashboard.
_PUBLIC_ROUTES = {
    ("POST", "/api/chat/message"),
    ("POST", "/api/leads"),
}
_PUBLIC_PREFIXES = {
    ("GET", "/api/chat/history/"),
}


def _is_public(method: str, path: str) -> bool:
    if (method, path) in _PUBLIC_ROUTES:
        return True
    if any(method == m and path.startswith(prefix) for m, prefix in _PUBLIC_PREFIXES):
        return True
    # /api/businesses/{business_id}/public-settings — business_id varies, so
    # match by shape rather than a fixed prefix.
    if method == "GET" and path.startswith("/api/businesses/") and path.endswith("/public-settings"):
        return True
    return False


class PublicRouteCORSMiddleware:
    """Allows any origin for public widget routes; defers everything else to
    the standard, origin-restricted CORSMiddleware further down the stack."""

    def __init__(self, app: ASGIApp):
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send):
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        headers = dict(scope["headers"])
        origin = headers.get(b"origin")
        method = scope["method"]
        path = scope["path"]

        if method == "OPTIONS":
            requested_method = headers.get(b"access-control-request-method", b"").decode()
            if origin and _is_public(requested_method, path):
                response = Response(status_code=200)
                response.headers["Access-Control-Allow-Origin"] = origin.decode()
                response.headers["Access-Control-Allow-Methods"] = "GET, POST, OPTIONS"
                response.headers["Access-Control-Allow-Headers"] = "*"
                response.headers["Vary"] = "Origin"
                await response(scope, receive, send)
                return
            await self.app(scope, receive, send)
            return

        if origin and _is_public(method, path):

            async def send_wrapper(message):
                if message["type"] == "http.response.start":
                    # The standard CORSMiddleware further down the stack also adds its
                    # own Access-Control-Allow-Origin/Vary headers when this origin
                    # happens to also be in the restrictive allowlist (e.g. testing the
                    # widget from the dashboard's own localhost origin). Strip those
                    # before adding ours so the browser sees exactly one value --
                    # Chrome rejects a response with a duplicated
                    # Access-Control-Allow-Origin header as an invalid CORS response,
                    # even though the underlying request succeeded.
                    message["headers"] = [
                        (k, v)
                        for k, v in message["headers"]
                        if k.lower() not in (b"access-control-allow-origin", b"vary")
                    ]
                    message["headers"].append((b"access-control-allow-origin", origin))
                    message["headers"].append((b"vary", b"Origin"))
                await send(message)

            await self.app(scope, receive, send_wrapper)
            return

        await self.app(scope, receive, send)
