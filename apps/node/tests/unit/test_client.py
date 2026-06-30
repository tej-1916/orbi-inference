"""Bounded HTTP policy and gateway payload tests."""

import random
from collections.abc import Callable

import httpx
import pytest

from orbi_node.client import GatewayClient
from orbi_node.errors import AuthenticationError, PermanentHTTPError, RetryExhaustedError
from orbi_node.schemas import WorkerCapabilities


def capabilities() -> WorkerCapabilities:
    return WorkerCapabilities(
        hostname_hash="a" * 16,
        architecture="x86_64",
        operating_system="linux",
        cpu_count=4,
        memory_bytes=1024,
    )


async def make_client(
    make_settings: Callable[..., object],
    handler: Callable[[httpx.Request], httpx.Response],
    sleeps: list[float],
) -> GatewayClient:
    async def sleep(delay: float) -> None:
        sleeps.append(delay)

    return GatewayClient(
        make_settings(),  # type: ignore[arg-type]
        transport=httpx.MockTransport(handler),
        sleep=sleep,
        random_source=random.Random(0),  # noqa: S311 - deterministic test jitter
    )


async def test_401_triggers_controlled_recovery(
    make_settings: Callable[..., object],
) -> None:
    calls = 0

    def handler(_request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        return httpx.Response(401)

    client = await make_client(make_settings, handler, [])
    with pytest.raises(AuthenticationError):
        await client.pull("worker-jwt")
    assert calls == 1
    await client.close()


async def test_403_is_not_retried(make_settings: Callable[..., object]) -> None:
    calls = 0

    def handler(_request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        return httpx.Response(403)

    client = await make_client(make_settings, handler, [])
    with pytest.raises(PermanentHTTPError) as captured:
        await client.pull("worker-jwt")
    assert captured.value.status_code == 403
    assert calls == 1
    await client.close()


async def test_429_respects_retry_after(make_settings: Callable[..., object]) -> None:
    responses = iter(
        [
            httpx.Response(429, headers={"Retry-After": "2"}),
            httpx.Response(200, json={"request": None}),
        ]
    )
    sleeps: list[float] = []
    client = await make_client(make_settings, lambda _request: next(responses), sleeps)
    assert await client.pull("worker-jwt") is None
    assert sleeps == [2.0]
    await client.close()


async def test_500_uses_bounded_backoff(make_settings: Callable[..., object]) -> None:
    calls = 0
    sleeps: list[float] = []

    def handler(_request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        return httpx.Response(500)

    client = await make_client(make_settings, handler, sleeps)
    with pytest.raises(RetryExhaustedError):
        await client.pull("worker-jwt")
    assert calls == 3
    assert len(sleeps) == 2
    assert sleeps[0] <= 0.1
    assert sleeps[1] <= 0.2
    await client.close()


async def test_heartbeat_exposes_capabilities_but_no_secrets(
    make_settings: Callable[..., object],
) -> None:
    captured: dict[str, object] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["headers"] = dict(request.headers)
        captured["body"] = request.content.decode()
        return httpx.Response(204)

    client = await make_client(make_settings, handler, [])
    await client.heartbeat("worker-jwt", capabilities())
    body = str(captured["body"])
    assert "text_generation" in body
    assert "hostname_hash" in body
    assert "enrollment" not in body
    assert "worker-jwt" not in body
    await client.close()
