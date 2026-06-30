"""In-memory worker JWT lifecycle management."""

import asyncio
from collections.abc import Callable

from orbi_node.client import GatewayClient
from orbi_node.schemas import WorkerCapabilities, WorkerToken

Clock = Callable[[], float]


class TokenManager:
    """Own the scoped worker JWT without persisting or logging it."""

    def __init__(
        self,
        client: GatewayClient,
        capabilities: WorkerCapabilities,
        renewal_margin_seconds: float,
        *,
        clock: Clock | None = None,
    ) -> None:
        self._client = client
        self._capabilities = capabilities
        self._renewal_margin = renewal_margin_seconds
        self._clock = clock or asyncio.get_running_loop().time
        self._token: str | None = None
        self._expires_at = 0.0
        self._lock = asyncio.Lock()

    async def enroll(self) -> None:
        async with self._lock:
            self._store(await self._client.enroll(self._capabilities))

    async def get(self) -> str:
        async with self._lock:
            if self._token is None:
                self._store(await self._client.enroll(self._capabilities))
            elif self._clock() >= self._expires_at - self._renewal_margin:
                self._store(await self._client.renew(self._token))
            assert self._token is not None
            return self._token

    async def re_enroll(self) -> None:
        """Attempt controlled recovery; one-time credentials may cause a clean failure."""
        async with self._lock:
            self._token = None
            self._expires_at = 0.0
            self._store(await self._client.enroll(self._capabilities))

    def clear(self) -> None:
        self._token = None
        self._expires_at = 0.0

    @property
    def available(self) -> bool:
        """Return whether an authenticated heartbeat can be attempted."""
        return self._token is not None

    def _store(self, response: WorkerToken) -> None:
        self._token = response.access_token
        self._expires_at = self._clock() + response.expires_in
