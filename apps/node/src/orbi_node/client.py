"""Gateway-only HTTP client with finite timeouts and bounded retry behavior."""

import asyncio
import random
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime
from email.utils import parsedate_to_datetime
from typing import Any

import httpx

from orbi_node.config import NodeSettings
from orbi_node.errors import AuthenticationError, PermanentHTTPError, RetryExhaustedError
from orbi_node.schemas import (
    InferenceRequest,
    InferenceResult,
    WorkerCapabilities,
    WorkerToken,
)

Sleep = Callable[[float], Awaitable[None]]


class GatewayClient:
    """Restrict node network access to the configured ORBI gateway."""

    def __init__(
        self,
        settings: NodeSettings,
        *,
        transport: httpx.AsyncBaseTransport | None = None,
        sleep: Sleep = asyncio.sleep,
        random_source: random.Random | None = None,
    ) -> None:
        self._settings = settings
        self._sleep = sleep
        self._random = random_source or random.SystemRandom()
        self._http = httpx.AsyncClient(
            base_url=str(settings.core_url).rstrip("/"),
            timeout=httpx.Timeout(settings.http_timeout_seconds),
            transport=transport,
            follow_redirects=False,
        )

    async def close(self) -> None:
        await self._http.aclose()

    async def enroll(self, capabilities: WorkerCapabilities) -> WorkerToken:
        response = await self._request(
            "POST",
            "/internal/workers/register",
            json={
                "enrollment_token": self._settings.enrollment_token,
                "provider_type": self._settings.provider_type,
                "name": self._settings.name,
                "supported_models": self._settings.supported_models,
                "capabilities": capabilities.model_dump(mode="json"),
            },
            authenticated=False,
        )
        return WorkerToken.model_validate(response.json())

    async def renew(self, token: str) -> WorkerToken:
        response = await self._request(
            "POST", "/internal/workers/renew", token=token
        )
        return WorkerToken.model_validate(response.json())

    async def heartbeat(
        self, token: str, capabilities: WorkerCapabilities, *, draining: bool = False
    ) -> None:
        await self._request(
            "POST",
            "/internal/workers/heartbeat",
            token=token,
            json={
                "status": "DRAINING" if draining else "ONLINE",
                "current_queue_depth": 0,
                "capabilities": capabilities.model_dump(mode="json"),
            },
        )

    async def pull(self, token: str) -> InferenceRequest | None:
        response = await self._request("GET", "/internal/workers/request", token=token)
        request_data = response.json().get("request")
        return None if request_data is None else InferenceRequest.model_validate(request_data)

    async def submit_result(self, token: str, result: InferenceResult) -> None:
        await self._request(
            "POST",
            "/internal/workers/result",
            token=token,
            json=result.model_dump(mode="json"),
        )

    async def submit_error(
        self,
        token: str,
        *,
        request_id: str,
        retryable: bool,
        error_code: str,
        message: str,
    ) -> None:
        await self._request(
            "POST",
            "/internal/workers/error",
            token=token,
            json={
                "request_id": request_id,
                "retryable": retryable,
                "error_code": error_code,
                "message": message,
            },
        )

    async def _request(
        self,
        method: str,
        path: str,
        *,
        token: str | None = None,
        authenticated: bool = True,
        json: dict[str, Any] | None = None,
    ) -> httpx.Response:
        headers: dict[str, str] = {}
        if authenticated:
            if not token:
                raise AuthenticationError("Worker token is unavailable.")
            headers["Authorization"] = f"Bearer {token}"

        attempts = self._settings.max_http_retries + 1
        for attempt in range(attempts):
            try:
                response = await self._http.request(
                    method, path, headers=headers, json=json
                )
            except (httpx.TimeoutException, httpx.NetworkError):
                if attempt + 1 >= attempts:
                    raise RetryExhaustedError() from None
                await self._sleep(self._backoff(attempt))
                continue

            if 200 <= response.status_code < 300:
                return response
            if response.status_code == 401:
                raise AuthenticationError()
            if response.status_code == 429:
                if attempt + 1 >= attempts:
                    raise RetryExhaustedError()
                await self._sleep(self._retry_after(response, attempt))
                continue
            if response.status_code >= 500:
                if attempt + 1 >= attempts:
                    raise RetryExhaustedError()
                await self._sleep(self._backoff(attempt))
                continue
            raise PermanentHTTPError(response.status_code)
        raise RetryExhaustedError()

    def _backoff(self, attempt: int) -> float:
        ceiling = min(
            self._settings.retry_max_seconds,
            self._settings.retry_base_seconds * (2**attempt),
        )
        return self._random.uniform(0, ceiling)

    def _retry_after(self, response: httpx.Response, attempt: int) -> float:
        value = response.headers.get("Retry-After")
        if value:
            try:
                return min(max(float(value), 0.0), self._settings.retry_max_seconds)
            except ValueError:
                try:
                    target = parsedate_to_datetime(value)
                    if target.tzinfo is None:
                        target = target.replace(tzinfo=UTC)
                    delay = (target - datetime.now(UTC)).total_seconds()
                    return min(max(delay, 0.0), self._settings.retry_max_seconds)
                except (TypeError, ValueError, OverflowError):
                    pass
        return self._backoff(attempt)
