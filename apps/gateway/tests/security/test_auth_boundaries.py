"""Security-boundary tests for revoked API keys and worker JWTs."""

from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace
from uuid import uuid4

import pytest
from argon2 import PasswordHasher
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from starlette.datastructures import State
from starlette.requests import Request

from orbi_gateway.dependencies import require_api_key, require_worker
from orbi_gateway.errors import OrbiError
from orbi_gateway.models import APIKey, Worker
from orbi_gateway.services.api_keys import APIKeyService
from orbi_gateway.services.worker_tokens import WorkerJWTService


class ScalarResult:
    """Minimal SQLAlchemy result substitute for dependency tests."""

    def __init__(self, value: object) -> None:
        self._value = value

    def scalar_one_or_none(self) -> object:
        return self._value


class FakeSession:
    """Return one preselected model without implementing database behaviour."""

    def __init__(self, value: object) -> None:
        self._value = value

    async def execute(self, _: object) -> ScalarResult:
        return ScalarResult(self._value)


class AllowingRateLimiter:
    """Permit one request so the test isolates credential checks."""

    async def allow_minute(self, _: str, __: int) -> bool:
        return True


def make_request(**state_values: object) -> Request:
    """Create a Starlette request with a minimal application state."""
    app = SimpleNamespace(state=State(state_values))
    return Request({"type": "http", "headers": [], "app": app})


async def test_revoked_api_key_is_rejected_before_route_execution() -> None:
    hasher = PasswordHasher(time_cost=1, memory_cost=8192)
    service = APIKeyService("p" * 48, hasher)
    generated = service.generate("test")
    record = APIKey(
        project_id=uuid4(),
        key_id=generated.key_id,
        display_prefix=generated.display_prefix,
        secret_hash=generated.secret_hash,
        environment="test",
        scopes=["chat"],
        revoked_at=datetime.now(UTC),
        daily_requests_date=datetime.now(UTC).date(),
    )
    request = make_request(api_key_service=service, rate_limiter=AllowingRateLimiter())

    with pytest.raises(OrbiError) as captured:
        await require_api_key(
            request,
            FakeSession(record),  # type: ignore[arg-type]
            f"Bearer {generated.raw_key}",
        )
    assert captured.value.code == "invalid_api_key"


async def test_worker_jwt_with_revoked_jti_is_rejected(tmp_path: Path) -> None:
    private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    private_path = tmp_path / "private.pem"
    public_path = tmp_path / "public.pem"
    private_path.write_bytes(
        private_key.private_bytes(
            serialization.Encoding.PEM,
            serialization.PrivateFormat.PKCS8,
            serialization.NoEncryption(),
        )
    )
    public_path.write_bytes(
        private_key.public_key().public_bytes(
            serialization.Encoding.PEM,
            serialization.PublicFormat.SubjectPublicKeyInfo,
        )
    )
    service = WorkerJWTService(
        private_path,
        public_path,
        issuer="orbi-core-test",
        audience="orbi-worker-test",
        ttl_seconds=600,
    )
    worker_id = uuid4()
    token, _ = service.issue(worker_id)
    worker = Worker(
        id=worker_id,
        provider_type="local",
        name="revoked-worker",
        status="ONLINE",
        supported_models=[],
        capabilities={},
        token_jti="different-jti",  # noqa: S106
    )
    request = make_request(worker_jwt_service=service)

    with pytest.raises(OrbiError) as captured:
        await require_worker(
            request,
            FakeSession(worker),  # type: ignore[arg-type]
            f"Bearer {token}",
        )
    assert captured.value.code == "invalid_worker_token"
