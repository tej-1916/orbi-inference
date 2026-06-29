"""Circuit-breaker unit tests using a bounded in-memory Redis substitute."""

from orbi_gateway.services.circuit_breaker import CircuitBreakerService, CircuitState


class FakeRedis:
    def __init__(self) -> None:
        self.data: dict[str, dict[bytes, bytes]] = {}

    async def hgetall(self, key: str) -> dict[bytes, bytes]:
        return self.data.get(key, {})

    async def hset(self, key: str, mapping: dict[str, str | int | float]) -> int:
        bucket = self.data.setdefault(key, {})
        for field, value in mapping.items():
            bucket[field.encode()] = str(value).encode()
        return len(mapping)

    async def expire(self, key: str, seconds: int) -> bool:
        return key in self.data and seconds > 0

    async def delete(self, key: str) -> int:
        return int(self.data.pop(key, None) is not None)


async def test_circuit_breaker_opens_at_threshold_and_closes_on_success() -> None:
    service = CircuitBreakerService(FakeRedis(), threshold=5, cooldown_seconds=120)
    for _ in range(4):
        assert (await service.record_failure("worker-1")).state is CircuitState.CLOSED
    assert (await service.record_failure("worker-1")).state is CircuitState.OPEN
    assert (await service.record_success("worker-1")).state is CircuitState.CLOSED
