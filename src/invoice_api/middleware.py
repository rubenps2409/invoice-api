import logging
import time

from starlette.types import ASGIApp, Message, Receive, Scope, Send

logger = logging.getLogger("invoice_api.request")

# Polled every few seconds by whatever watches the service: not worth an INFO line.
_QUIET_PATHS = frozenset({"/api/health"})


class RequestLogMiddleware:
    """One log line per HTTP request: method, path, status and duration.

    Pure ASGI on purpose: BaseHTTPMiddleware runs the app in another task, which
    complicates cancellation and costs more per request. It never logs the query
    string, the headers, the body or the client IP.
    """

    def __init__(self, app: ASGIApp):
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        started = time.perf_counter()
        status = 500  # what the client gets if the app fails before answering

        async def send_and_remember_status(message: Message) -> None:
            nonlocal status
            if message["type"] == "http.response.start":
                status = message["status"]
            await send(message)

        try:
            await self.app(scope, receive, send_and_remember_status)
        finally:
            duration_ms = round((time.perf_counter() - started) * 1000, 1)
            method, path = scope["method"], scope["path"]
            level = logging.DEBUG if path in _QUIET_PATHS else logging.INFO
            logger.log(
                level,
                "%s %s %d %.1fms",
                method,
                path,
                status,
                duration_ms,
                extra={
                    "method": method,
                    "path": path,
                    "status": status,
                    "duration_ms": duration_ms,
                },
            )
