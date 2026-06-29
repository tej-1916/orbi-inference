"""Worker liveness maintenance based on bounded heartbeat expiry."""

from datetime import UTC, datetime, timedelta

from sqlalchemy import update
from sqlalchemy.ext.asyncio import AsyncSession

from orbi_gateway.models import Worker


class WorkerHealthService:
    """Mark workers offline when their heartbeats stop; it does not make routing decisions."""

    def __init__(self, heartbeat_timeout_seconds: int = 90) -> None:
        if heartbeat_timeout_seconds < 30:
            raise ValueError("heartbeat timeout must be at least 30 seconds")
        self._timeout = heartbeat_timeout_seconds

    async def mark_stale_workers_offline(self, session: AsyncSession) -> int:
        """Mark non-draining workers offline after the configured heartbeat deadline."""
        cutoff = datetime.now(UTC) - timedelta(seconds=self._timeout)
        result = await session.execute(
            update(Worker)
            .where(
                Worker.status == "ONLINE",
                Worker.last_heartbeat.is_not(None),
                Worker.last_heartbeat < cutoff,
            )
            .values(status="OFFLINE")
        )
        return result.rowcount or 0
