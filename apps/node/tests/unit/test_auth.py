"""Worker token lifecycle tests."""

from uuid import uuid4

from orbi_node.auth import TokenManager
from orbi_node.schemas import WorkerCapabilities, WorkerToken


class FakeClient:
    def __init__(self) -> None:
        self.renewed: list[str] = []

    async def enroll(self, _capabilities: WorkerCapabilities) -> WorkerToken:
        return WorkerToken(
            worker_id=uuid4(), access_token="first", expires_in=100  # noqa: S106
        )

    async def renew(self, token: str) -> WorkerToken:
        self.renewed.append(token)
        return WorkerToken(
            worker_id=uuid4(), access_token="second", expires_in=100  # noqa: S106
        )


async def test_expiring_jwt_is_renewed() -> None:
    now = 0.0
    client = FakeClient()
    capabilities = WorkerCapabilities(
        hostname_hash="a" * 16,
        architecture="x86_64",
        operating_system="linux",
        cpu_count=1,
    )
    manager = TokenManager(  # type: ignore[arg-type]
        client, capabilities, renewal_margin_seconds=10, clock=lambda: now
    )
    assert await manager.get() == "first"
    now = 91.0
    assert await manager.get() == "second"
    assert client.renewed == ["first"]
