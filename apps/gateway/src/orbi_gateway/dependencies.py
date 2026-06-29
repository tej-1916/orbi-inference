"""FastAPI dependency providers and authentication boundaries."""

from collections.abc import AsyncIterator, Callable
from datetime import UTC, datetime
from typing import Annotated
from uuid import UUID

from fastapi import Depends, Header, Request
from jwt import InvalidTokenError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from orbi_gateway.errors import OrbiError
from orbi_gateway.models import APIKey, Project, Worker
from orbi_gateway.services.api_keys import APIKeyService


async def get_session(request: Request) -> AsyncIterator[AsyncSession]:
    """Yield one transaction-scoped database session."""
    async for session in request.app.state.database.session():
        yield session


async def require_api_key(
    request: Request,
    session: Annotated[AsyncSession, Depends(get_session)],
    authorization: Annotated[str | None, Header()] = None,
) -> APIKey:
    """Authenticate a client API key and enforce revocation, expiry, and rate limits."""
    if authorization is None or not authorization.startswith("Bearer "):
        raise OrbiError("invalid_api_key", "A valid bearer API key is required.", 401)
    raw_key = authorization.removeprefix("Bearer ").strip()
    service: APIKeyService = request.app.state.api_key_service
    parsed = service.parse(raw_key)
    if parsed is None:
        raise OrbiError("invalid_api_key", "A valid bearer API key is required.", 401)
    environment, key_id, secret = parsed
    record = (
        await session.execute(
            select(APIKey)
            .join(Project, Project.id == APIKey.project_id)
            .where(APIKey.key_id == key_id, Project.is_active.is_(True))
            .with_for_update(of=APIKey)
        )
    ).scalar_one_or_none()
    if (
        record is None
        or record.environment != environment
        or not service.verify_secret(secret, record.secret_hash)
        or not service.is_record_active(record.expires_at, record.revoked_at)
    ):
        raise OrbiError("invalid_api_key", "A valid bearer API key is required.", 401)
    now = datetime.now(UTC)
    today = now.date()
    if record.daily_requests_date != today:
        record.daily_requests_date = today
        record.daily_requests_used = 0
    if record.daily_requests_used >= record.daily_req_limit:
        raise OrbiError("daily_request_limit_exceeded", "Daily request limit exceeded.", 429)
    if not await request.app.state.rate_limiter.allow_minute(record.key_id, record.rpm_limit):
        raise OrbiError("rate_limit_exceeded", "Per-minute request limit exceeded.", 429)
    record.daily_requests_used += 1
    record.last_used_at = now
    return record


async def require_admin(
    request: Request,
    authorization: Annotated[str | None, Header()] = None,
) -> None:
    """Authenticate the bootstrap administrator using an Argon2id hash."""
    if authorization is None or not authorization.startswith("Bearer "):
        raise OrbiError("admin_auth_required", "Administrator authentication is required.", 401)
    token = authorization.removeprefix("Bearer ").strip()
    if not request.app.state.admin_token_verifier(token):
        raise OrbiError("admin_auth_required", "Administrator authentication is required.", 401)


async def require_worker(
    request: Request,
    session: Annotated[AsyncSession, Depends(get_session)],
    authorization: Annotated[str | None, Header()] = None,
) -> Worker:
    """Verify a scoped worker JWT and ensure its JTI is still current and not revoked."""
    if authorization is None or not authorization.startswith("Bearer "):
        raise OrbiError("worker_auth_required", "Worker authentication is required.", 401)
    token = authorization.removeprefix("Bearer ").strip()
    try:
        claims = request.app.state.worker_jwt_service.verify(token)
        worker_id = UUID(str(claims["sub"]))
        jti = str(claims["jti"])
    except (InvalidTokenError, ValueError, KeyError):
        raise OrbiError(
            "invalid_worker_token", "Worker token is invalid or expired.", 401
        ) from None
    worker = (
        await session.execute(select(Worker).where(Worker.id == worker_id))
    ).scalar_one_or_none()
    if worker is None or worker.revoked_at is not None or worker.token_jti != jti:
        raise OrbiError("invalid_worker_token", "Worker token is invalid or revoked.", 401)
    request.state.worker_claims = claims
    return worker


def require_api_scope(required_scope: str) -> Callable[..., object]:
    """Create a dependency that enforces one API-key scope after authentication."""

    async def dependency(api_key: Annotated[APIKey, Depends(require_api_key)]) -> APIKey:
        if required_scope not in api_key.scopes and "*" not in api_key.scopes:
            raise OrbiError("insufficient_scope", "API key lacks the required scope.", 403)
        return api_key

    return dependency


def require_worker_scope(required_scope: str) -> Callable[..., object]:
    """Create a dependency that enforces one worker JWT scope."""

    async def dependency(
        request: Request,
        worker: Annotated[Worker, Depends(require_worker)],
    ) -> Worker:
        scopes = request.state.worker_claims.get("scope", [])
        if not isinstance(scopes, list) or required_scope not in scopes:
            raise OrbiError("insufficient_worker_scope", "Worker token lacks scope.", 403)
        return worker

    return dependency


SessionDep = Annotated[AsyncSession, Depends(get_session)]
APIKeyDep = Annotated[APIKey, Depends(require_api_key)]
ChatAPIKeyDep = Annotated[APIKey, Depends(require_api_scope("chat"))]
ModelsAPIKeyDep = Annotated[APIKey, Depends(require_api_scope("models:read"))]
UsageAPIKeyDep = Annotated[APIKey, Depends(require_api_scope("usage:read"))]
AdminDep = Annotated[None, Depends(require_admin)]
WorkerDep = Annotated[Worker, Depends(require_worker)]
WorkerHeartbeatDep = Annotated[Worker, Depends(require_worker_scope("worker:heartbeat"))]
WorkerPullDep = Annotated[Worker, Depends(require_worker_scope("worker:pull"))]
WorkerResultDep = Annotated[Worker, Depends(require_worker_scope("worker:result"))]
WorkerErrorDep = Annotated[Worker, Depends(require_worker_scope("worker:error"))]
WorkerRenewDep = Annotated[Worker, Depends(require_worker_scope("worker:renew"))]
