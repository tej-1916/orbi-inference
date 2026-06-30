"""Periodic heartbeat sender."""

import asyncio
from contextlib import suppress

import structlog

from orbi_node.auth import TokenManager
from orbi_node.client import GatewayClient
from orbi_node.errors import AuthenticationError, NodeError
from orbi_node.schemas import WorkerCapabilities


class HeartbeatService:
    def __init__(
        self,
        client: GatewayClient,
        tokens: TokenManager,
        capabilities: WorkerCapabilities,
        interval_seconds: float,
    ) -> None:
        self._client = client
        self._tokens = tokens
        self._capabilities = capabilities
        self._interval = interval_seconds
        self._stop = asyncio.Event()

    async def run(self) -> None:
        logger = structlog.get_logger(__name__)
        while not self._stop.is_set():
            try:
                await self._client.heartbeat(
                    await self._tokens.get(), self._capabilities
                )
            except AuthenticationError:
                await logger.awarning("heartbeat_authentication_failed")
                raise
            except NodeError as exc:
                await logger.awarning("heartbeat_failed", error_code=exc.code)
            try:
                await asyncio.wait_for(self._stop.wait(), timeout=self._interval)
            except TimeoutError:
                pass

    async def stop(self) -> None:
        self._stop.set()
        if not self._tokens.available:
            return
        with suppress(AuthenticationError, NodeError):
            await self._client.heartbeat(
                await self._tokens.get(), self._capabilities, draining=True
            )
