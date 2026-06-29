"""Transactional hard-budget reservation and reconciliation services."""

from dataclasses import dataclass
from datetime import UTC, date, datetime
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from orbi_gateway.models import Project


@dataclass(frozen=True, slots=True)
class BudgetSnapshot:
    daily_limit: int
    daily_used: int
    monthly_limit: int
    monthly_used: int


class BudgetExceededError(ValueError):
    """Raised when accepting a request would exceed a hard project token limit."""


def enforce_budget(snapshot: BudgetSnapshot, requested_tokens: int) -> None:
    """Reject a request if its reserved token ceiling exceeds either hard limit."""
    if requested_tokens < 1:
        raise ValueError("requested_tokens must be positive")
    if snapshot.daily_used + requested_tokens > snapshot.daily_limit:
        raise BudgetExceededError("daily token limit would be exceeded")
    if snapshot.monthly_used + requested_tokens > snapshot.monthly_limit:
        raise BudgetExceededError("monthly token limit would be exceeded")


class BudgetService:
    """Serialize project reservations so concurrent requests cannot oversubscribe a budget."""

    async def reserve(
        self, session: AsyncSession, project_id: UUID, requested_tokens: int
    ) -> tuple[Project, date, date]:
        """Lock a project row, reset usage periods when needed, and reserve tokens atomically."""
        project = (
            await session.execute(select(Project).where(Project.id == project_id).with_for_update())
        ).scalar_one()
        today = datetime.now(UTC).date()
        month = today.replace(day=1)
        if project.daily_usage_date != today:
            project.daily_usage_date = today
            project.daily_tokens_used = 0
        if project.monthly_usage_month != month:
            project.monthly_usage_month = month
            project.monthly_tokens_used = 0
        enforce_budget(
            BudgetSnapshot(
                daily_limit=project.daily_token_limit,
                daily_used=project.daily_tokens_used,
                monthly_limit=project.monthly_token_limit,
                monthly_used=project.monthly_tokens_used,
            ),
            requested_tokens,
        )
        project.daily_tokens_used += requested_tokens
        project.monthly_tokens_used += requested_tokens
        return project, today, month

    async def reconcile(
        self,
        session: AsyncSession,
        *,
        project_id: UUID,
        reserved_tokens: int,
        actual_tokens: int,
        budget_day: date,
        budget_month: date,
    ) -> None:
        """Replace a reservation with actual usage without corrupting a newer accounting period."""
        project = (
            await session.execute(select(Project).where(Project.id == project_id).with_for_update())
        ).scalar_one()
        delta = actual_tokens - reserved_tokens
        if project.daily_usage_date == budget_day:
            project.daily_tokens_used = max(0, project.daily_tokens_used + delta)
        if project.monthly_usage_month == budget_month:
            project.monthly_tokens_used = max(0, project.monthly_tokens_used + delta)

    async def release(
        self,
        session: AsyncSession,
        *,
        project_id: UUID,
        reserved_tokens: int,
        budget_day: date,
        budget_month: date,
    ) -> None:
        """Release a reservation for a request that reached a terminal state without a result."""
        await self.reconcile(
            session,
            project_id=project_id,
            reserved_tokens=reserved_tokens,
            actual_tokens=0,
            budget_day=budget_day,
            budget_month=budget_month,
        )
