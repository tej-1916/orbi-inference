"""Atomic fixed-window request limiting in Redis with mandatory TTLs."""

from datetime import UTC, datetime

from redis.asyncio import Redis


class RateLimitService:
    """Apply a per-key minute window without creating immortal Redis keys."""

    def __init__(self, redis: Redis) -> None:
        self._redis = redis

    async def allow_minute(self, key_id: str, rpm_limit: int) -> bool:
        now = datetime.now(UTC)
        window = now.strftime("%Y%m%d%H%M")
        key = f"orbi:ratelimit:{key_id}:{window}"
        count = await self._redis.incr(key)
        if count == 1:
            await self._redis.expire(key, 120)
        return count <= rpm_limit
