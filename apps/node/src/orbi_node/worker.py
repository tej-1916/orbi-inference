"""Single-flight node orchestration and graceful shutdown."""

import asyncio
from contextlib import suppress

import structlog

from orbi_node.auth import TokenManager
from orbi_node.client import GatewayClient
from orbi_node.config import NodeSettings
from orbi_node.errors import AuthenticationError, NodeError, UnknownRequestError
from orbi_node.heartbeat import HeartbeatService
from orbi_node.runtimes.base import InferenceRuntime
from orbi_node.schemas import InferenceRequest, InferenceResult, WorkerCapabilities


class OrbiWorker:
    """Poll and process at most one assigned request at a time."""

    def __init__(
        self,
        settings: NodeSettings,
        client: GatewayClient,
        runtime: InferenceRuntime,
        capabilities: WorkerCapabilities,
    ) -> None:
        self._settings = settings
        self._client = client
        self._runtime = runtime
        self._tokens = TokenManager(
            client,
            capabilities,
            settings.jwt_renewal_margin_seconds,
        )
        self._heartbeats = HeartbeatService(
            client,
            self._tokens,
            capabilities,
            settings.heartbeat_interval_seconds,
        )
        self._stopping = asyncio.Event()
        self._process_lock = asyncio.Lock()
        self._active_request: InferenceRequest | None = None
        self._heartbeat_task: asyncio.Task[None] | None = None

    async def run(self) -> None:
        logger = structlog.get_logger(__name__)
        try:
            await self._runtime.load()
            await self._tokens.enroll()
        except NodeError as exc:
            await logger.aerror("worker_start_failed", error_code=exc.code)
            await self.close()
            return
        self._heartbeat_task = asyncio.create_task(self._heartbeats.run())
        await logger.ainfo("worker_started", worker_name=self._settings.name)
        try:
            while not self._stopping.is_set():
                try:
                    await self.process_once()
                except AuthenticationError:
                    await logger.awarning("worker_authentication_recovery")
                    try:
                        await self._tokens.re_enroll()
                    except AuthenticationError:
                        await logger.aerror("worker_authentication_shutdown")
                        self._stopping.set()
                        break
                except NodeError as exc:
                    await logger.awarning("worker_cycle_failed", error_code=exc.code)
                try:
                    await asyncio.wait_for(
                        self._stopping.wait(),
                        timeout=self._settings.poll_interval_seconds,
                    )
                except TimeoutError:
                    pass
        finally:
            await self.close()

    async def process_once(self) -> bool:
        if self._stopping.is_set() or self._process_lock.locked():
            return False
        async with self._process_lock:
            if self._stopping.is_set():
                return False
            token = await self._tokens.get()
            request = await self._client.pull(token)
            if request is None:
                return False
            self._active_request = request
            try:
                result = await self._runtime.generate(request)
                await self._submit_assigned(token, result)
            except asyncio.CancelledError:
                with suppress(NodeError):
                    await self._client.submit_error(
                        token,
                        request_id=str(request.id),
                        retryable=True,
                        error_code="inference_cancelled",
                        message="Inference was cancelled during worker shutdown.",
                    )
                raise
            except NodeError as exc:
                await self._client.submit_error(
                    token,
                    request_id=str(request.id),
                    retryable=exc.retryable,
                    error_code=exc.code,
                    message=exc.safe_message,
                )
            finally:
                self._active_request = None
            return True

    async def stop(self) -> None:
        """Stop new polling; the active inference is allowed to finish."""
        self._stopping.set()

    async def close(self) -> None:
        self._stopping.set()
        await self._heartbeats.stop()
        if self._heartbeat_task is not None:
            self._heartbeat_task.cancel()
            with suppress(asyncio.CancelledError, AuthenticationError):
                await self._heartbeat_task
        await self._runtime.close()
        self._tokens.clear()
        await self._client.close()

    async def _submit_assigned(self, token: str, result: InferenceResult) -> None:
        if self._active_request is None or result.request_id != self._active_request.id:
            raise UnknownRequestError()
        await self._client.submit_result(token, result)
