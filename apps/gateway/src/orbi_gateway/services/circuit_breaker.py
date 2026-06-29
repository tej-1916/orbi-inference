"""Redis-backed three-state circuit breaker with bounded keys and explicit cooldowns."""

from dataclasses import dataclass
from enum import StrEnum
from time import time
from typing import Protocol


class CircuitState(StrEnum):
    CLOSED = "CLOSED"
    OPEN = "OPEN"
    HALF_OPEN = "HALF_OPEN"


class RedisHashClient(Protocol):
    async def hgetall(self, key: str) -> dict[bytes, bytes]: ...
    async def hset(self, key: str, mapping: dict[str, str | int | float]) -> int: ...
    async def expire(self, key: str, seconds: int) -> bool: ...
    async def delete(self, key: str) -> int: ...


@dataclass(frozen=True, slots=True)
class CircuitSnapshot:
    state: CircuitState
    failures: int
    opened_at: float | None


class CircuitBreakerService:
    """Track worker failures without allowing Redis keys to grow without bounds."""

    def __init__(self, redis: RedisHashClient, threshold: int, cooldown_seconds: int) -> None:
        self._redis = redis
        self._threshold = threshold
        self._cooldown = cooldown_seconds

    async def get(self, worker_id: str) -> CircuitSnapshot:
        """Return the effective state, transitioning OPEN to HALF_OPEN after cooldown."""
        key = self._key(worker_id)
        raw = await self._redis.hgetall(key)
        if not raw:
            return CircuitSnapshot(CircuitState.CLOSED, 0, None)
        state = CircuitState(raw[b"state"].decode())
        failures = int(raw.get(b"failures", b"0"))
        opened_at = float(raw[b"opened_at"]) if b"opened_at" in raw else None
        if (
            state is CircuitState.OPEN
            and opened_at is not None
            and time() - opened_at >= self._cooldown
        ):
            state = CircuitState.HALF_OPEN
            await self._redis.hset(key, mapping={"state": state.value})
            await self._redis.expire(key, self._cooldown * 3)
        return CircuitSnapshot(state, failures, opened_at)

    async def record_failure(self, worker_id: str) -> CircuitSnapshot:
        """Increment failures and open the circuit at the configured threshold."""
        current = await self.get(worker_id)
        failures = current.failures + 1
        state = CircuitState.OPEN if failures >= self._threshold else current.state
        opened_at = time() if state is CircuitState.OPEN else current.opened_at
        key = self._key(worker_id)
        mapping: dict[str, str | int | float] = {"state": state.value, "failures": failures}
        if opened_at is not None:
            mapping["opened_at"] = opened_at
        await self._redis.hset(key, mapping=mapping)
        await self._redis.expire(key, self._cooldown * 3)
        return CircuitSnapshot(state, failures, opened_at)

    async def record_success(self, worker_id: str) -> CircuitSnapshot:
        """Close the circuit after a successful normal or canary request."""
        await self._redis.delete(self._key(worker_id))
        return CircuitSnapshot(CircuitState.CLOSED, 0, None)

    @staticmethod
    def _key(worker_id: str) -> str:
        return f"orbi:circuit:{worker_id}"
