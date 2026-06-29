"""Worker enrollment, heartbeat, durable request claiming, and result commitment endpoints."""

from datetime import UTC, datetime

from fastapi import APIRouter, Request
from sqlalchemy import select

from orbi_gateway.dependencies import (
    SessionDep,
    WorkerErrorDep,
    WorkerHeartbeatDep,
    WorkerPullDep,
    WorkerRenewDep,
    WorkerResultDep,
)
from orbi_gateway.errors import OrbiError
from orbi_gateway.models import Worker, WorkerEnrollmentToken
from orbi_gateway.schemas.api import (
    WorkerErrorRequest,
    WorkerHeartbeatRequest,
    WorkerRegisterRequest,
    WorkerResultRequest,
    WorkerTokenResponse,
)

router = APIRouter(prefix="/internal/workers", tags=["internal-workers"])


@router.post("/register", response_model=WorkerTokenResponse, status_code=201)
async def register_worker(
    payload: WorkerRegisterRequest,
    session: SessionDep,
    request: Request,
) -> WorkerTokenResponse:
    """Consume a one-time enrollment token and issue a scoped short-lived worker JWT."""
    prefix = "orbi_node_v1_"
    remainder = payload.enrollment_token.removeprefix(prefix)
    if (
        not payload.enrollment_token.startswith(prefix)
        or len(remainder) != 56
        or remainder[12] != "_"
    ):
        raise OrbiError("invalid_enrollment_token", "Enrollment token is invalid.", 401)
    token_id = remainder[:12]
    token_record = (
        await session.execute(
            select(WorkerEnrollmentToken)
            .where(WorkerEnrollmentToken.token_id == token_id)
            .with_for_update()
        )
    ).scalar_one_or_none()
    now = datetime.now(UTC)
    if (
        token_record is None
        or token_record.consumed_at is not None
        or token_record.expires_at <= now
        or request.app.state.worker_enrollment_service.parse_and_verify(
            payload.enrollment_token, token_record.secret_hash
        )
        is None
    ):
        raise OrbiError("invalid_enrollment_token", "Enrollment token is invalid or expired.", 401)

    worker = Worker(
        provider_type=payload.provider_type,
        name=payload.name,
        status="ONLINE",
        supported_models=payload.supported_models,
        capabilities=payload.capabilities,
        last_heartbeat=now,
    )
    session.add(worker)
    await session.flush()
    access_token, jti = request.app.state.worker_jwt_service.issue(worker.id)
    worker.token_jti = jti
    token_record.consumed_at = now
    return WorkerTokenResponse(
        worker_id=worker.id,
        access_token=access_token,
        expires_in=request.app.state.settings.worker_token_ttl_seconds,
    )


@router.post("/heartbeat", status_code=204)
async def heartbeat(
    payload: WorkerHeartbeatRequest,
    worker: WorkerHeartbeatDep,
    session: SessionDep,
) -> None:
    """Update only the authenticated worker's own health and capability record."""
    worker.status = payload.status
    worker.current_queue_depth = payload.current_queue_depth
    worker.capabilities = payload.capabilities
    worker.last_heartbeat = datetime.now(UTC)
    await session.flush()


@router.get("/request")
async def pull_request(
    worker: WorkerPullDep, session: SessionDep, request: Request
) -> dict[str, object]:
    """Claim one compatible request using PostgreSQL SKIP LOCKED semantics."""
    if worker.status != "ONLINE":
        return {"request": None}
    claimed = await request.app.state.queue_service.claim_next(
        session,
        worker,
        request.app.state.settings.worker_lease_seconds,
    )
    if claimed is None:
        return {"request": None}
    return {
        "request": {
            "id": str(claimed.id),
            "model": claimed.resolved_model,
            "payload": claimed.payload,
            "retry_count": claimed.retry_count,
            "lease_expires": claimed.lease_expires.isoformat() if claimed.lease_expires else None,
        }
    }


@router.post("/result", status_code=204)
async def submit_result(
    payload: WorkerResultRequest,
    worker: WorkerResultDep,
    session: SessionDep,
    request: Request,
) -> None:
    """Atomically accept one result only from the request's currently assigned worker."""
    accepted = await request.app.state.queue_service.commit_result(
        session,
        request_id=payload.request_id,
        worker=worker,
        result=payload.result,
        input_tokens=payload.input_tokens,
        output_tokens=payload.output_tokens,
        latency_ms=payload.latency_ms,
    )
    if not accepted:
        raise OrbiError(
            "result_not_accepted",
            "The request is complete, unassigned, or assigned to another worker.",
            409,
        )


@router.post("/renew", response_model=WorkerTokenResponse)
async def renew_worker_token(
    worker: WorkerRenewDep,
    session: SessionDep,
    request: Request,
) -> WorkerTokenResponse:
    """Rotate a valid worker JWT and immediately invalidate the previous JTI."""
    access_token, jti = request.app.state.worker_jwt_service.issue(worker.id)
    worker.token_jti = jti
    await session.flush()
    return WorkerTokenResponse(
        worker_id=worker.id,
        access_token=access_token,
        expires_in=request.app.state.settings.worker_token_ttl_seconds,
    )


@router.post("/error", status_code=204)
async def submit_error(
    payload: WorkerErrorRequest,
    worker: WorkerErrorDep,
    session: SessionDep,
    request: Request,
) -> None:
    """Record a sanitized worker failure without accepting stack traces or secret material."""
    accepted = await request.app.state.queue_service.record_error(
        session,
        request_id=payload.request_id,
        worker=worker,
        retryable=payload.retryable,
        error_code=payload.error_code,
        message=payload.message,
    )
    if not accepted:
        raise OrbiError(
            "error_not_accepted",
            "The request is complete, unassigned, or assigned to another worker.",
            409,
        )
