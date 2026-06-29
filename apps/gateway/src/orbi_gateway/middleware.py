"""Small ASGI security middleware that does not inspect or log request bodies."""

from collections.abc import Awaitable, Callable
from typing import Any
from uuid import uuid4

from starlette.responses import JSONResponse

type ASGIMessage = dict[str, Any]
type Receive = Callable[[], Awaitable[ASGIMessage]]
type Send = Callable[[ASGIMessage], Awaitable[None]]
type ASGIApp = Callable[[dict[str, Any], Receive, Send], Awaitable[None]]


class RequestBodyTooLarge(Exception):
    """Internal control-flow exception; it never includes request data."""


class SecurityMiddleware:
    """Limit request bytes and add non-cacheable API security headers and request IDs."""

    def __init__(self, app: ASGIApp, max_body_bytes: int) -> None:
        if max_body_bytes < 1024:
            raise ValueError("max_body_bytes must be at least 1024")
        self.app = app
        self.max_body_bytes = max_body_bytes

    async def __call__(self, scope: dict[str, Any], receive: Receive, send: Send) -> None:
        if scope.get("type") != "http":
            await self.app(scope, receive, send)
            return

        headers = dict(scope.get("headers", []))
        content_length = headers.get(b"content-length")
        if content_length is not None:
            try:
                if int(content_length) > self.max_body_bytes:
                    await self._reject(scope, receive, send)
                    return
            except ValueError:
                await self._reject(scope, receive, send, code="invalid_content_length")
                return

        consumed = 0
        response_started = False
        request_id = str(uuid4())
        scope.setdefault("state", {})["request_id"] = request_id

        async def limited_receive() -> ASGIMessage:
            nonlocal consumed
            message = await receive()
            if message.get("type") == "http.request":
                consumed += len(message.get("body", b""))
                if consumed > self.max_body_bytes:
                    raise RequestBodyTooLarge
            return message

        async def secure_send(message: ASGIMessage) -> None:
            nonlocal response_started
            if message.get("type") == "http.response.start":
                response_started = True
                response_headers = list(message.get("headers", []))
                response_headers.extend(
                    [
                        (b"x-content-type-options", b"nosniff"),
                        (b"cache-control", b"no-store"),
                        (b"x-orbi-request-id", request_id.encode()),
                    ]
                )
                message["headers"] = response_headers
            await send(message)

        try:
            await self.app(scope, limited_receive, secure_send)
        except RequestBodyTooLarge:
            if response_started:
                raise
            await self._reject(scope, receive, send)

    async def _reject(
        self,
        scope: dict[str, Any],
        receive: Receive,
        send: Send,
        *,
        code: str = "request_body_too_large",
    ) -> None:
        response = JSONResponse(
            status_code=413 if code == "request_body_too_large" else 400,
            content={
                "error": {
                    "code": code,
                    "message": "Request body is invalid or exceeds the configured limit.",
                }
            },
            headers={"Cache-Control": "no-store", "X-Content-Type-Options": "nosniff"},
        )
        await response(scope, receive, send)
