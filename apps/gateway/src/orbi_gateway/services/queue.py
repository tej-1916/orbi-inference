"""Transactional PostgreSQL queue operations using row locks and atomic result commitment."""

from datetime import UTC, datetime, timedelta
from uuid import UUID

from sqlalchemy import or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from orbi_gateway.models import APIKey, OrbiRequest, UsageRecord, Worker
from orbi_gateway.services.budget import BudgetService


class QueueService:
    """Own queue state transitions; route handlers must not mutate requests directly."""

    def __init__(self, budget_service: BudgetService) -> None:
        self._budget_service = budget_service

    async def claim_next(
        self, session: AsyncSession, worker: Worker, lease_seconds: int
    ) -> OrbiRequest | None:
        """Claim one compatible queued request without blocking competing workers."""
        now = datetime.now(UTC)
        compatibility = OrbiRequest.required_capabilities.op("<@")(worker.capabilities)
        statement = (
            select(OrbiRequest)
            .where(
                OrbiRequest.status == "QUEUED",
                OrbiRequest.expires_at > now,
                compatibility,
                or_(
                    OrbiRequest.resolved_model.in_(worker.supported_models),
                    OrbiRequest.model_alias.in_(worker.supported_models),
                ),
            )
            .order_by(OrbiRequest.priority.asc(), OrbiRequest.created_at.asc())
            .with_for_update(skip_locked=True)
            .limit(1)
        )
        request = (await session.execute(statement)).scalar_one_or_none()
        if request is None:
            return None
        request.status = "ASSIGNED"
        request.assigned_to = worker.id
        request.lease_expires = now + timedelta(seconds=lease_seconds)
        return request

    async def commit_result(
        self,
        session: AsyncSession,
        *,
        request_id: UUID,
        worker: Worker,
        result: dict[str, object],
        input_tokens: int,
        output_tokens: int,
        latency_ms: int,
    ) -> bool:
        """Atomically accept at most one result from the currently assigned worker."""
        now = datetime.now(UTC)
        statement = (
            update(OrbiRequest)
            .where(
                OrbiRequest.id == request_id,
                OrbiRequest.assigned_to == worker.id,
                OrbiRequest.result.is_(None),
                OrbiRequest.status.in_(["ASSIGNED", "STARTING", "RUNNING", "STREAMING"]),
            )
            .values(
                status="COMPLETED",
                result=result,
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                completed_at=now,
                lease_expires=None,
            )
            .returning(
                OrbiRequest.project_id,
                OrbiRequest.api_key_id,
                OrbiRequest.resolved_model,
                OrbiRequest.reserved_tokens,
                OrbiRequest.budget_day,
                OrbiRequest.budget_month,
            )
        )
        row = (await session.execute(statement)).one_or_none()
        if row is None:
            return False
        total_tokens = input_tokens + output_tokens
        await self._budget_service.reconcile(
            session,
            project_id=row.project_id,
            reserved_tokens=row.reserved_tokens,
            actual_tokens=total_tokens,
            budget_day=row.budget_day,
            budget_month=row.budget_month,
        )
        await session.execute(
            update(APIKey)
            .where(APIKey.id == row.api_key_id)
            .values(
                total_requests=APIKey.total_requests + 1,
                total_tokens=APIKey.total_tokens + total_tokens,
            )
        )
        session.add(
            UsageRecord(
                request_id=request_id,
                project_id=row.project_id,
                api_key_id=row.api_key_id,
                worker_id=worker.id,
                provider_type=worker.provider_type,
                model_id=row.resolved_model,
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                latency_ms=latency_ms,
            )
        )
        return True

    async def record_error(
        self,
        session: AsyncSession,
        *,
        request_id: UUID,
        worker: Worker,
        retryable: bool,
        error_code: str,
        message: str,
    ) -> bool:
        """Record a safe worker error, requeue within budget, or fail and release reservation."""
        request = (
            await session.execute(
                select(OrbiRequest)
                .where(
                    OrbiRequest.id == request_id,
                    OrbiRequest.assigned_to == worker.id,
                    OrbiRequest.result.is_(None),
                    OrbiRequest.status.in_(["ASSIGNED", "STARTING", "RUNNING", "STREAMING"]),
                )
                .with_for_update()
            )
        ).scalar_one_or_none()
        if request is None:
            return False

        request.error_detail = {"code": error_code, "message": message}
        request.assigned_to = None
        request.lease_expires = None
        if retryable and request.retry_count < request.max_retries:
            request.retry_count += 1
            request.status = "QUEUED"
            return True

        request.status = "FAILED_FINAL"
        await self._budget_service.release(
            session,
            project_id=request.project_id,
            reserved_tokens=request.reserved_tokens,
            budget_day=request.budget_day,
            budget_month=request.budget_month,
        )
        return True

    async def recover_expired_leases(self, session: AsyncSession) -> int:
        """Requeue retryable expired leases and fail requests whose retry budget is exhausted."""
        now = datetime.now(UTC)
        retryable = await session.execute(
            update(OrbiRequest)
            .where(
                OrbiRequest.status.in_(["ASSIGNED", "STARTING", "RUNNING", "STREAMING"]),
                OrbiRequest.lease_expires < now,
                OrbiRequest.retry_count < OrbiRequest.max_retries,
                OrbiRequest.result.is_(None),
            )
            .values(
                status="QUEUED",
                assigned_to=None,
                lease_expires=None,
                retry_count=OrbiRequest.retry_count + 1,
            )
        )
        terminal_rows = (
            await session.execute(
                update(OrbiRequest)
                .where(
                    OrbiRequest.status.in_(["ASSIGNED", "STARTING", "RUNNING", "STREAMING"]),
                    OrbiRequest.lease_expires < now,
                    OrbiRequest.retry_count >= OrbiRequest.max_retries,
                    OrbiRequest.result.is_(None),
                )
                .values(
                    status="FAILED_FINAL",
                    assigned_to=None,
                    lease_expires=None,
                    error_detail={"code": "retry_budget_exhausted"},
                )
                .returning(
                    OrbiRequest.project_id,
                    OrbiRequest.reserved_tokens,
                    OrbiRequest.budget_day,
                    OrbiRequest.budget_month,
                )
            )
        ).all()
        expired_rows = (
            await session.execute(
                update(OrbiRequest)
                .where(
                    OrbiRequest.status == "QUEUED",
                    OrbiRequest.expires_at < now,
                    OrbiRequest.result.is_(None),
                )
                .values(status="EXPIRED", error_detail={"code": "queue_ttl_expired"})
                .returning(
                    OrbiRequest.project_id,
                    OrbiRequest.reserved_tokens,
                    OrbiRequest.budget_day,
                    OrbiRequest.budget_month,
                )
            )
        ).all()
        for row in [*terminal_rows, *expired_rows]:
            await self._budget_service.release(
                session,
                project_id=row.project_id,
                reserved_tokens=row.reserved_tokens,
                budget_day=row.budget_day,
                budget_month=row.budget_month,
            )
        return retryable.rowcount or 0
