"""Single-flight, assignment, shutdown, and cancellation tests."""

import asyncio
from collections.abc import Callable
from uuid import uuid4

import pytest

from orbi_node.errors import NodeError
from orbi_node.runtime import MockInferenceRuntime
from orbi_node.schemas import (
    InferenceRequest,
    InferenceResult,
    WorkerCapabilities,
    WorkerToken,
)
from orbi_node.worker import OrbiWorker


class FakeClient:
    def __init__(self, assigned: InferenceRequest | None) -> None:
        self.assigned = assigned
        self.pull_calls = 0
        self.results: list[InferenceResult] = []
        self.errors: list[dict[str, object]] = []
        self.closed = False

    async def enroll(self, _capabilities: WorkerCapabilities) -> WorkerToken:
        return WorkerToken(
            worker_id=uuid4(), access_token="token", expires_in=3600  # noqa: S106
        )

    async def renew(self, _token: str) -> WorkerToken:
        return await self.enroll(capabilities())

    async def pull(self, _token: str) -> InferenceRequest | None:
        self.pull_calls += 1
        assigned, self.assigned = self.assigned, None
        return assigned

    async def submit_result(self, _token: str, result: InferenceResult) -> None:
        self.results.append(result)

    async def submit_error(self, _token: str, **error: object) -> None:
        self.errors.append(error)

    async def heartbeat(
        self,
        _token: str,
        _capabilities: WorkerCapabilities,
        *,
        draining: bool = False,
    ) -> None:
        return None

    async def close(self) -> None:
        self.closed = True


def capabilities() -> WorkerCapabilities:
    return WorkerCapabilities(
        hostname_hash="a" * 16,
        architecture="x86_64",
        operating_system="linux",
        cpu_count=1,
    )


def assigned_request() -> InferenceRequest:
    return InferenceRequest(
        id=uuid4(),
        model="test/model",
        payload={"messages": [{"role": "user", "content": "private"}]},
    )


def worker(
    make_settings: Callable[..., object],
    client: FakeClient,
    runtime: MockInferenceRuntime,
) -> OrbiWorker:
    return OrbiWorker(  # type: ignore[arg-type]
        make_settings(), client, runtime, capabilities()
    )


async def test_only_one_request_is_processed_at_a_time(
    make_settings: Callable[..., object],
) -> None:
    client = FakeClient(assigned_request())
    runtime = MockInferenceRuntime(delay_seconds=0.05)
    await runtime.load()
    node = worker(make_settings, client, runtime)
    first, second = await asyncio.gather(node.process_once(), node.process_once())
    assert sorted([first, second]) == [False, True]
    assert client.pull_calls == 1
    assert len(client.results) == 1


async def test_result_uses_exact_assigned_request_id(
    make_settings: Callable[..., object],
) -> None:
    assigned = assigned_request()
    client = FakeClient(assigned)
    runtime = MockInferenceRuntime()
    await runtime.load()
    await worker(make_settings, client, runtime).process_once()
    assert client.results[0].request_id == assigned.id


async def test_unknown_request_id_cannot_be_submitted(
    make_settings: Callable[..., object],
) -> None:
    class WrongRuntime(MockInferenceRuntime):
        async def generate(self, request: InferenceRequest) -> InferenceResult:
            result = await super().generate(request)
            return result.model_copy(update={"request_id": uuid4()})

    client = FakeClient(assigned_request())
    runtime = WrongRuntime()
    await runtime.load()
    await worker(make_settings, client, runtime).process_once()
    assert client.results == []
    assert client.errors[0]["error_code"] == "unknown_request_id"


async def test_graceful_shutdown_stops_polling(
    make_settings: Callable[..., object],
) -> None:
    client = FakeClient(assigned_request())
    runtime = MockInferenceRuntime()
    await runtime.load()
    node = worker(make_settings, client, runtime)
    await node.stop()
    assert await node.process_once() is False
    assert client.pull_calls == 0


async def test_cancellation_during_inference_is_reported_safely(
    make_settings: Callable[..., object],
) -> None:
    client = FakeClient(assigned_request())
    runtime = MockInferenceRuntime(delay_seconds=10)
    await runtime.load()
    node = worker(make_settings, client, runtime)
    task = asyncio.create_task(node.process_once())
    await asyncio.sleep(0)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert client.errors[0]["error_code"] == "inference_cancelled"
    assert client.results == []


async def test_controlled_runtime_failure_is_reported(
    make_settings: Callable[..., object],
) -> None:
    client = FakeClient(assigned_request())
    runtime = MockInferenceRuntime(
        failure=NodeError("model_failure", "Model failed.", retryable=False)
    )
    await runtime.load()
    await worker(make_settings, client, runtime).process_once()
    assert client.errors[0]["error_code"] == "model_failure"
    assert client.errors[0]["retryable"] is False
