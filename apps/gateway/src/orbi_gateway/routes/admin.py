"""Bootstrap administration endpoints; no browser dashboard is included in Phase 1."""

from datetime import UTC, datetime, timedelta
from uuid import UUID

from fastapi import APIRouter, Request
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from orbi_gateway.dependencies import AdminDep, SessionDep
from orbi_gateway.errors import OrbiError
from orbi_gateway.models import APIKey, ModelAlias, Project, Worker, WorkerEnrollmentToken
from orbi_gateway.schemas.api import (
    APIKeyCreatedResponse,
    APIKeyCreateRequest,
    ModelAliasCreateRequest,
    ModelAliasResponse,
    ProjectCreateRequest,
    ProjectResponse,
    WorkerEnrollmentCreatedResponse,
    WorkerEnrollmentCreateRequest,
)

router = APIRouter(prefix="/admin", tags=["admin"])


@router.post("/api-keys", response_model=APIKeyCreatedResponse, status_code=201)
async def create_api_key(
    payload: APIKeyCreateRequest,
    _: AdminDep,
    session: SessionDep,
    request: Request,
) -> APIKeyCreatedResponse:
    """Create an API key and return its raw value exactly once."""
    project = (
        await session.execute(select(Project).where(Project.id == payload.project_id))
    ).scalar_one_or_none()
    if project is None:
        raise OrbiError("project_not_found", "Project does not exist.", 404)
    generated = request.app.state.api_key_service.generate(payload.environment)
    record = APIKey(
        project_id=payload.project_id,
        key_id=generated.key_id,
        display_prefix=generated.display_prefix,
        secret_hash=generated.secret_hash,
        environment=generated.environment,
        name=payload.name,
        scopes=payload.scopes,
        expires_at=payload.expires_at,
        rpm_limit=payload.rpm_limit,
        daily_req_limit=payload.daily_req_limit,
    )
    session.add(record)
    await session.flush()
    return APIKeyCreatedResponse(
        id=record.id, key=generated.raw_key, display_prefix=record.display_prefix
    )


@router.post("/worker-enrollments", response_model=WorkerEnrollmentCreatedResponse, status_code=201)
async def create_worker_enrollment(
    payload: WorkerEnrollmentCreateRequest,
    _: AdminDep,
    session: SessionDep,
    request: Request,
) -> WorkerEnrollmentCreatedResponse:
    """Create a short-lived one-time worker enrollment token."""
    generated = request.app.state.worker_enrollment_service.generate()
    expires_at = datetime.now(UTC) + timedelta(seconds=payload.expires_in_seconds)
    session.add(
        WorkerEnrollmentToken(
            token_id=generated.token_id,
            secret_hash=generated.secret_hash,
            expires_at=expires_at,
        )
    )
    return WorkerEnrollmentCreatedResponse(
        enrollment_token=generated.raw_token,
        expires_at=expires_at,
    )


@router.post("/projects", response_model=ProjectResponse, status_code=201)
async def create_project(
    payload: ProjectCreateRequest,
    _: AdminDep,
    session: SessionDep,
) -> ProjectResponse:
    """Create a project tenant before issuing API keys."""
    project = Project(
        name=payload.name,
        slug=payload.slug,
        owner_id=payload.owner_id,
        daily_token_limit=payload.daily_token_limit,
        monthly_token_limit=payload.monthly_token_limit,
    )
    session.add(project)
    try:
        await session.flush()
    except IntegrityError as exc:
        raise OrbiError("project_conflict", "Project slug already exists.", 409) from exc
    return ProjectResponse(id=project.id, name=project.name, slug=project.slug)


@router.post("/model-aliases", response_model=ModelAliasResponse, status_code=201)
async def create_model_alias(
    payload: ModelAliasCreateRequest,
    _: AdminDep,
    session: SessionDep,
) -> ModelAliasResponse:
    """Register a provider-independent model alias used by public requests."""
    alias = ModelAlias(
        alias=payload.alias,
        display_name=payload.display_name,
        model_id=payload.model_id,
        min_vram_gb=payload.min_vram_gb,
        required_capabilities=payload.required_capabilities,
        supports_streaming=payload.supports_streaming,
        supports_tools=payload.supports_tools,
        max_context_tokens=payload.max_context_tokens,
    )
    session.add(alias)
    try:
        await session.flush()
    except IntegrityError as exc:
        raise OrbiError("model_alias_conflict", "Model alias already exists.", 409) from exc
    return ModelAliasResponse(alias=alias.alias, model_id=alias.model_id)


@router.post("/api-keys/{api_key_id}/revoke", status_code=204)
async def revoke_api_key(
    api_key_id: UUID,
    _: AdminDep,
    session: SessionDep,
) -> None:
    """Immediately revoke an API key without deleting its audit and usage history."""
    record = (
        await session.execute(select(APIKey).where(APIKey.id == api_key_id).with_for_update())
    ).scalar_one_or_none()
    if record is None:
        raise OrbiError("api_key_not_found", "API key does not exist.", 404)
    if record.revoked_at is None:
        record.revoked_at = datetime.now(UTC)


@router.post("/workers/{worker_id}/revoke", status_code=204)
async def revoke_worker(
    worker_id: UUID,
    _: AdminDep,
    session: SessionDep,
) -> None:
    """Revoke the worker's current JWT and suspend further queue claims."""
    worker = (
        await session.execute(select(Worker).where(Worker.id == worker_id).with_for_update())
    ).scalar_one_or_none()
    if worker is None:
        raise OrbiError("worker_not_found", "Worker does not exist.", 404)
    worker.revoked_at = worker.revoked_at or datetime.now(UTC)
    worker.status = "SUSPENDED"
    worker.token_jti = None
