"""Bound request buffering and public submissions before parsing or side effects.

The submission limiter is process-local. Shared deployment limits belong at the
reverse proxy; only its trusted client address is used, never raw forwarded headers.
"""

import math
import threading
import time
from collections import OrderedDict
from collections.abc import Callable

from starlette.responses import JSONResponse
from starlette.types import ASGIApp, Message, Receive, Scope, Send

MAX_REQUEST_BYTES = 1024 * 1024
# Ten MB of accepted attachments expands to about fourteen MB in base64 JSON.
MAX_SUPPORT_REQUEST_BYTES = 15 * 1024 * 1024
SUPPORT_ATTACHMENT_PATHS = frozenset({
    "/api/v1/support/requests", "/api/v1/support/public-requests",
})
PUBLIC_SUBMISSION_LIMITS = {
    "/api/v1/support/public-requests": 5,
    "/api/v1/surveys": 10,
}


class SubmissionLimiter:
    """Fixed windows with bounded state; full tables reject new keys until expiry."""

    def __init__(
        self,
        *,
        window_seconds: int = 600,
        max_entries: int = 10_000,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._window_seconds = window_seconds
        self._max_entries = max_entries
        self._clock = clock
        self._lock = threading.Lock()
        self._entries: OrderedDict[tuple[str, str], tuple[int, float]] = OrderedDict()

    def retry_after(self, path: str, client: str, limit: int) -> int | None:
        with self._lock:
            now = self._clock()
            # Every entry has the same window duration and retains insertion order.
            while self._entries:
                first = next(iter(self._entries))
                if self._entries[first][1] > now:
                    break
                self._entries.popitem(last=False)
            key = (path, client)
            entry = self._entries.get(key)
            if entry is None:
                if len(self._entries) >= self._max_entries:
                    return max(1, math.ceil(next(iter(self._entries.values()))[1] - now))
                self._entries[key] = (1, now + self._window_seconds)
                return None
            count, expires_at = entry
            if count >= limit:
                return max(1, math.ceil(expires_at - now))
            self._entries[key] = (count + 1, expires_at)
            return None


class RequestSecurityMiddleware:
    def __init__(
        self,
        app: ASGIApp,
        *,
        max_request_bytes: int = MAX_REQUEST_BYTES,
        max_support_bytes: int = MAX_SUPPORT_REQUEST_BYTES,
        limiter: SubmissionLimiter | None = None,
    ) -> None:
        self.app = app
        self.max_request_bytes = max_request_bytes
        self.max_support_bytes = max_support_bytes
        self.limiter = limiter or SubmissionLimiter()

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        path = scope["path"].rstrip("/")
        limit = (
            self.max_support_bytes if path in SUPPORT_ATTACHMENT_PATHS else self.max_request_bytes
        )
        lengths = [value for name, value in scope.get("headers", ()) if name == b"content-length"]
        if lengths:
            length = lengths[0].strip()
            if len(lengths) != 1 or not length.isdigit():
                await self._reject(scope, receive, send, 400, "invalid_content_length")
                return
            length = length.lstrip(b"0") or b"0"
            if len(length) > len(str(limit)) or int(length) > limit:
                await self._reject(scope, receive, send, 413, "request_too_large")
                return
        submission_path = scope["path"]
        if scope["method"] == "POST" and submission_path in PUBLIC_SUBMISSION_LIMITS:
            client = scope.get("client")
            client_host = client[0] if client else "unknown"
            retry_after = self.limiter.retry_after(
                submission_path, client_host, PUBLIC_SUBMISSION_LIMITS[submission_path]
            )
            if retry_after is not None:
                await self._reject(
                    scope, receive, send, 429, "submission_rate_limited",
                    headers={"Retry-After": str(retry_after)},
                )
                return

        # Buffer no more than the limit before downstream JSON parsing begins.
        # Checking only Content-Length would allow missing or dishonest headers.
        body = bytearray()
        while True:
            message = await receive()
            if message["type"] == "http.disconnect":
                return
            chunk = message.get("body", b"")
            if len(body) + len(chunk) > limit:
                await self._reject(scope, receive, send, 413, "request_too_large")
                return
            body.extend(chunk)
            if not message.get("more_body", False):
                break
        buffered_body = bytes(body)
        del body
        replayed = False

        async def replay() -> Message:
            nonlocal replayed
            if replayed:
                return await receive()
            replayed = True
            return {"type": "http.request", "body": buffered_body, "more_body": False}

        await self.app(scope, replay, send)

    @staticmethod
    async def _reject(
        scope: Scope, receive: Receive, send: Send, status: int, code: str,
        *, headers: dict[str, str] | None = None,
    ) -> None:
        messages = {
            400: "The request length is invalid.",
            413: "The request is too large.",
            429: "Too many submissions. Please try again later.",
        }
        response = JSONResponse(
            {"detail": {"code": code, "message": messages[status]}},
            status_code=status, headers=headers,
        )
        await response(scope, receive, send)
