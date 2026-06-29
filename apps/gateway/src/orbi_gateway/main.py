"""FastAPI application factory for the ORBI Phase 1 gateway and control plane."""

import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager, suppress

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerifyMismatchError
from fastapi import FastAPI
from fastapi.exceptions import RequestValidationError
from redis.asyncio import Redis

from orbi_gateway.config import get_settings
from orbi_gateway.database import Database
from orbi_gateway.errors import (
    OrbiError,
    orbi_error_handler,
    unexpected_error_handler,
    validation_error_handler,
)
from orbi_gateway.logging import configure_logging
from orbi_gateway.middleware import SecurityMiddleware
from orbi_gateway.routes import admin, chat, health, models, usage
from orbi_gateway.routes.internal import workers
from orbi_gateway.services.api_keys import APIKeyService
from orbi_gateway.services.budget import BudgetService
from orbi_gateway.services.circuit_breaker import CircuitBreakerService
from orbi_gateway.services.queue import QueueService
from orbi_gateway.services.rate_limit import RateLimitService
from orbi_gateway.services.worker_health import WorkerHealthService
from orbi_gateway.services.worker_tokens import WorkerEnrollmentService, WorkerJWTService


async def _lease_recovery_loop(app: FastAPI) -> None:
    """Periodically recover expired worker leases until application shutdown."""
    interval = app.state.settings.lease_recovery_interval_seconds
    while True:
        await asyncio.sleep(interval)
        try:
            async for session in app.state.database.session():
                await app.state.queue_service.recover_expired_leases(session)
                await app.state.worker_health.mark_stale_workers_offline(session)
        except Exception as exc:  # The maintenance loop must survive transient dependency failures.
            import structlog

            await structlog.get_logger(__name__).aerror(
                "maintenance_cycle_failed", exception_type=type(exc).__name__
            )


def create_app() -> FastAPI:
    """Create a fully configured ORBI application without import-time side effects."""
    settings = get_settings()
    configure_logging(settings.log_level)

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        app.state.settings = settings
        app.state.database = Database(settings)
        app.state.redis = Redis.from_url(settings.redis_url, decode_responses=False)
        app.state.api_key_service = APIKeyService(settings.api_key_pepper.get_secret_value())
        app.state.worker_enrollment_service = WorkerEnrollmentService(
            settings.worker_enrollment_pepper.get_secret_value()
        )
        app.state.worker_jwt_service = WorkerJWTService(
            settings.jwt_private_key_path,
            settings.jwt_public_key_path,
            settings.jwt_issuer,
            settings.jwt_audience,
            settings.worker_token_ttl_seconds,
        )
        app.state.rate_limiter = RateLimitService(app.state.redis)
        app.state.budget_service = BudgetService()
        app.state.queue_service = QueueService(app.state.budget_service)
        app.state.worker_health = WorkerHealthService()
        app.state.circuit_breaker = CircuitBreakerService(
            app.state.redis,
            settings.circuit_failure_threshold,
            settings.circuit_cooldown_seconds,
        )
        admin_hasher = PasswordHasher()
        expected_admin_hash = settings.admin_token_hash.get_secret_value()
        admin_pepper = settings.admin_token_pepper.get_secret_value()

        def verify_admin(token: str) -> bool:
            try:
                return admin_hasher.verify(expected_admin_hash, f"{token}:{admin_pepper}")
            except (VerifyMismatchError, InvalidHashError):
                return False

        app.state.admin_token_verifier = verify_admin
        recovery_task = asyncio.create_task(_lease_recovery_loop(app))
        try:
            yield
        finally:
            recovery_task.cancel()
            with suppress(asyncio.CancelledError):
                await recovery_task
            await app.state.redis.aclose()
            await app.state.database.dispose()

    app = FastAPI(title="ORBI Gateway", version="0.1.0", lifespan=lifespan)
    app.add_middleware(SecurityMiddleware, max_body_bytes=settings.max_request_body_bytes)
    app.add_exception_handler(OrbiError, orbi_error_handler)
    app.add_exception_handler(RequestValidationError, validation_error_handler)
    app.add_exception_handler(Exception, unexpected_error_handler)
    app.include_router(health.router)
    app.include_router(admin.router)
    app.include_router(models.router)
    app.include_router(chat.router)
    app.include_router(usage.router)
    app.include_router(workers.router)
    return app
