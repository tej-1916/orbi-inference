"""Docker-backed PostgreSQL lifecycle test for queue locking and single-result commitment."""

import os
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from orbi_gateway.models import APIKey, ModelAlias, OrbiRequest, Project, UsageRecord, Worker
from orbi_gateway.models.base import Base
from orbi_gateway.services.budget import BudgetService
from orbi_gateway.services.queue import QueueService

DATABASE_URL = os.getenv("TEST_DATABASE_URL")


@pytest.mark.integration
@pytest.mark.skipif(not DATABASE_URL, reason="TEST_DATABASE_URL is not configured")
async def test_request_lifecycle_queued_assigned_completed_once() -> None:
    """Prove SKIP LOCKED prevents a double claim and only one result can commit."""
    assert DATABASE_URL is not None
    engine = create_async_engine(DATABASE_URL)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    queue_service = QueueService(BudgetService())
    today = datetime.now(UTC).date()
    month = today.replace(day=1)

    try:
        async with engine.begin() as connection:
            await connection.run_sync(Base.metadata.drop_all)
            await connection.run_sync(Base.metadata.create_all)

        project_id = uuid4()
        api_key_id = uuid4()
        worker_id = uuid4()
        request_id = uuid4()

        async with session_factory() as session, session.begin():
            session.add_all(
                [
                    Project(
                        id=project_id,
                        name="Integration Project",
                        slug="integration-project",
                        owner_id=uuid4(),
                        daily_tokens_used=100,
                        monthly_tokens_used=100,
                        daily_usage_date=today,
                        monthly_usage_month=month,
                    ),
                    APIKey(
                        id=api_key_id,
                        project_id=project_id,
                        key_id="Integration1",
                        display_prefix="orbi_test_v1_Integration1",
                        secret_hash="$argon2id$v=19$m=65536,t=3,p=4$test$test",  # noqa: S106
                        environment="test",
                        scopes=["chat"],
                    ),
                    ModelAlias(
                        alias="orbi-default",
                        model_id="test/model",
                        required_capabilities={"text_generation": True},
                    ),
                    Worker(
                        id=worker_id,
                        provider_type="docker",
                        name="integration-worker",
                        status="ONLINE",
                        supported_models=["test/model"],
                        capabilities={"text_generation": True},
                    ),
                    OrbiRequest(
                        id=request_id,
                        idempotency_key="integration-idempotency-key",
                        project_id=project_id,
                        api_key_id=api_key_id,
                        model_alias="orbi-default",
                        resolved_model="test/model",
                        payload={"model": "orbi-default", "messages": []},
                        required_capabilities={"text_generation": True},
                        status="QUEUED",
                        expires_at=datetime.now(UTC) + timedelta(minutes=5),
                        reserved_tokens=100,
                        budget_day=today,
                        budget_month=month,
                    ),
                ]
            )

        first_session = session_factory()
        second_session = session_factory()
        try:
            await first_session.begin()
            await second_session.begin()
            first_worker = await first_session.get(Worker, worker_id)
            second_worker = await second_session.get(Worker, worker_id)
            assert first_worker is not None
            assert second_worker is not None

            first_claim = await queue_service.claim_next(first_session, first_worker, 120)
            second_claim = await queue_service.claim_next(second_session, second_worker, 120)

            assert first_claim is not None
            assert first_claim.id == request_id
            assert second_claim is None
            await first_session.commit()
            await second_session.rollback()
        finally:
            await first_session.close()
            await second_session.close()

        result_payload = {
            "id": f"orbi-{request_id}",
            "object": "chat.completion",
            "choices": [
                {
                    "index": 0,
                    "message": {"role": "assistant", "content": "done"},
                    "finish_reason": "stop",
                }
            ],
        }

        async with session_factory() as session, session.begin():
            worker = await session.get(Worker, worker_id)
            assert worker is not None
            accepted = await queue_service.commit_result(
                session,
                request_id=request_id,
                worker=worker,
                result=result_payload,
                input_tokens=5,
                output_tokens=10,
                latency_ms=25,
            )
            assert accepted is True

        async with session_factory() as session, session.begin():
            worker = await session.get(Worker, worker_id)
            assert worker is not None
            duplicate_accepted = await queue_service.commit_result(
                session,
                request_id=request_id,
                worker=worker,
                result={"unexpected": "late duplicate"},
                input_tokens=5,
                output_tokens=10,
                latency_ms=30,
            )
            assert duplicate_accepted is False

        async with session_factory() as session:
            stored_request = await session.get(OrbiRequest, request_id)
            project = await session.get(Project, project_id)
            api_key = await session.get(APIKey, api_key_id)
            usage = (
                await session.execute(
                    select(UsageRecord).where(UsageRecord.request_id == request_id)
                )
            ).scalar_one()

            assert stored_request is not None
            assert stored_request.status == "COMPLETED"
            assert stored_request.result == result_payload
            assert usage.input_tokens == 5
            assert usage.output_tokens == 10
            assert project is not None
            assert project.daily_tokens_used == 15
            assert project.monthly_tokens_used == 15
            assert api_key is not None
            assert api_key.total_requests == 1
            assert api_key.total_tokens == 15
    finally:
        async with engine.begin() as connection:
            await connection.run_sync(Base.metadata.drop_all)
        await engine.dispose()
