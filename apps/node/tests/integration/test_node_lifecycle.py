"""Real PostgreSQL/Redis gateway-to-node-to-result lifecycle."""

import os
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import uuid4

import httpx
import pytest

from orbi_gateway.config import get_settings as get_gateway_settings
from orbi_gateway.main import create_app
from orbi_gateway.models import APIKey, ModelAlias, OrbiRequest, Project, WorkerEnrollmentToken
from orbi_gateway.models.base import Base
from orbi_node.client import GatewayClient
from orbi_node.hardware import discover_capabilities
from orbi_node.runtime import MockInferenceRuntime
from orbi_node.worker import OrbiWorker

DATABASE_URL = os.getenv("TEST_DATABASE_URL")
REDIS_URL = os.getenv("TEST_REDIS_URL")
ROOT = Path(__file__).parents[4]


@pytest.mark.integration
@pytest.mark.skipif(
    not DATABASE_URL or not REDIS_URL,
    reason="TEST_DATABASE_URL and TEST_REDIS_URL are required",
)
async def test_gateway_node_result_lifecycle(
    monkeypatch: pytest.MonkeyPatch,
    make_settings: Callable[..., object],
) -> None:
    assert DATABASE_URL is not None
    assert REDIS_URL is not None
    monkeypatch.setenv("ORBI_DATABASE_URL", DATABASE_URL)
    monkeypatch.setenv("ORBI_REDIS_URL", REDIS_URL)
    monkeypatch.setenv(
        "ORBI_JWT_PRIVATE_KEY_PATH", str(ROOT / "secrets/orbi_jwt_private.pem")
    )
    monkeypatch.setenv(
        "ORBI_JWT_PUBLIC_KEY_PATH", str(ROOT / "secrets/orbi_jwt_public.pem")
    )
    get_gateway_settings.cache_clear()
    app = create_app()

    async with app.router.lifespan_context(app):
        async with app.state.database.engine.begin() as connection:
            await connection.run_sync(Base.metadata.drop_all)
            await connection.run_sync(Base.metadata.create_all)
        assert await app.state.redis.ping() is True

        generated = app.state.worker_enrollment_service.generate()
        today = datetime.now(UTC).date()
        month = today.replace(day=1)
        request_id = uuid4()
        project_id = uuid4()
        api_key_id = uuid4()
        async with app.state.database.session_factory() as session, session.begin():
            session.add(
                WorkerEnrollmentToken(
                    token_id=generated.token_id,
                    secret_hash=generated.secret_hash,
                    expires_at=datetime.now(UTC) + timedelta(minutes=5),
                )
            )
            session.add(
                Project(
                    id=project_id,
                    name="Node Integration",
                    slug="node-integration",
                    owner_id=uuid4(),
                    daily_tokens_used=100,
                    monthly_tokens_used=100,
                    daily_usage_date=today,
                    monthly_usage_month=month,
                )
            )
            await session.flush()
            session.add(
                APIKey(
                    id=api_key_id,
                    project_id=project_id,
                    key_id="NodeIntegr01",
                    display_prefix="orbi_test_v1_NodeIntegr01",
                    secret_hash="$argon2id$v=19$m=65536,t=3,p=4$test$test",  # noqa: S106
                    environment="test",
                    scopes=["chat"],
                )
            )
            session.add(
                ModelAlias(
                    alias="orbi-default",
                    model_id="test/model",
                    required_capabilities={"text_generation": True},
                )
            )
            await session.flush()
            session.add(
                OrbiRequest(
                    id=request_id,
                    idempotency_key="node-lifecycle",
                    project_id=project_id,
                    api_key_id=api_key_id,
                    model_alias="orbi-default",
                    resolved_model="test/model",
                    payload={
                        "model": "orbi-default",
                        "messages": [{"role": "user", "content": "integration prompt"}],
                    },
                    required_capabilities={"text_generation": True},
                    status="QUEUED",
                    expires_at=datetime.now(UTC) + timedelta(minutes=5),
                    reserved_tokens=100,
                    budget_day=today,
                    budget_month=month,
                )
            )

        node_settings = make_settings(
            core_url="http://orbi.test",
            enrollment_id=generated.token_id,
            enrollment_secret=generated.raw_token[len(f"orbi_node_v1_{generated.token_id}_") :],
        )
        client = GatewayClient(  # type: ignore[arg-type]
            node_settings,
            transport=httpx.ASGITransport(app=app),
        )
        runtime = MockInferenceRuntime()
        node = OrbiWorker(  # type: ignore[arg-type]
            node_settings, client, runtime, discover_capabilities()
        )
        await runtime.load()
        assert await node.process_once() is True
        await node.close()

        async with app.state.database.session_factory() as session:
            stored = await session.get(OrbiRequest, request_id)
            assert stored is not None
            assert stored.status == "COMPLETED"
            assert stored.result is not None
            assert stored.result["id"] == f"orbi-{request_id}"
            assert stored.input_tokens is not None
            assert stored.output_tokens == 5

        async with app.state.database.engine.begin() as connection:
            await connection.run_sync(Base.metadata.drop_all)
    get_gateway_settings.cache_clear()
