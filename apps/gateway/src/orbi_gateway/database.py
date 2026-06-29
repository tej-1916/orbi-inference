"""Async SQLAlchemy engine and transaction-scoped session factory."""

from collections.abc import AsyncIterator

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from orbi_gateway.config import Settings


class Database:
    """Own the SQLAlchemy engine and provide transaction-scoped sessions."""

    def __init__(self, settings: Settings) -> None:
        self.engine = create_async_engine(settings.database_url, pool_pre_ping=True)
        self.session_factory = async_sessionmaker(self.engine, expire_on_commit=False)

    async def session(self) -> AsyncIterator[AsyncSession]:
        """Yield a session and commit once unless the caller already committed explicitly."""
        async with self.session_factory() as session:
            try:
                yield session
                if session.in_transaction():
                    await session.commit()
            except BaseException:
                if session.in_transaction():
                    await session.rollback()
                raise

    async def dispose(self) -> None:
        """Release all pooled database connections."""
        await self.engine.dispose()
