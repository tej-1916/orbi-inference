"""OpenAI-compatible chat request acceptance and bounded synchronous result waiting."""

import asyncio
from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, Header, Request
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from orbi_gateway.dependencies import ChatAPIKeyDep, SessionDep
from orbi_gateway.errors import OrbiError
from orbi_gateway.models import ModelAlias, OrbiRequest
from orbi_gateway.schemas.api import ChatCompletionRequest
from orbi_gateway.services.budget import BudgetExceededError
from orbi_gateway.services.idempotency import validate_idempotency_key

router = APIRouter(prefix="/v1", tags=["chat"])


@router.post("/chat/completions")
async def create_chat_completion(
    payload: ChatCompletionRequest,
    api_key: ChatAPIKeyDep,
    session: SessionDep,
    request: Request,
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
) -> dict[str, object]:
    """Queue a request and wait a bounded time for a worker-completed OpenAI-shaped result."""
    if payload.stream:
        raise OrbiError("streaming_not_available", "Streaming is deferred to Phase 2.", 400)
    try:
        idempotency_key = validate_idempotency_key(idempotency_key)
    except ValueError as exc:
        raise OrbiError("invalid_idempotency_key", str(exc), 400) from exc

    if idempotency_key is not None:
        existing = (
            await session.execute(
                select(OrbiRequest).where(
                    OrbiRequest.api_key_id == api_key.id,
                    OrbiRequest.idempotency_key == idempotency_key,
                )
            )
        ).scalar_one_or_none()
        if existing is not None:
            if existing.status == "COMPLETED" and existing.result is not None:
                return existing.result
            return {"id": str(existing.id), "object": "orbi.request", "status": existing.status}

    alias = (
        await session.execute(
            select(ModelAlias).where(
                ModelAlias.alias == payload.model, ModelAlias.is_active.is_(True)
            )
        )
    ).scalar_one_or_none()
    if alias is None:
        raise OrbiError("model_not_found", "Requested model alias is unavailable.", 404)
    # UTF-8 byte length is a conservative tokenizer-independent upper bound for prompt tokens.
    reserved_tokens = sum(len(message.content.encode("utf-8")) for message in payload.messages)
    reserved_tokens += payload.max_tokens
    try:
        project, budget_day, budget_month = await request.app.state.budget_service.reserve(
            session, api_key.project_id, reserved_tokens
        )
    except BudgetExceededError as exc:
        raise OrbiError("token_budget_exceeded", str(exc), 429) from exc

    record = OrbiRequest(
        idempotency_key=idempotency_key,
        project_id=project.id,
        api_key_id=api_key.id,
        model_alias=alias.alias,
        resolved_model=alias.model_id,
        payload=payload.model_dump(mode="json"),
        required_capabilities=alias.required_capabilities,
        priority=5,
        status="QUEUED",
        expires_at=datetime.now(UTC) + timedelta(minutes=5),
        reserved_tokens=reserved_tokens,
        budget_day=budget_day,
        budget_month=budget_month,
    )
    session.add(record)
    try:
        await session.flush()
    except IntegrityError as exc:
        raise OrbiError(
            "idempotency_conflict", "An equivalent request already exists.", 409
        ) from exc
    request_id = record.id

    # Commit before waiting so workers in other transactions can claim the request.
    await session.commit()

    deadline = (
        asyncio.get_running_loop().time() + request.app.state.settings.request_wait_timeout_seconds
    )
    while asyncio.get_running_loop().time() < deadline:
        async with request.app.state.database.session_factory() as polling_session:
            current = await polling_session.get(OrbiRequest, request_id)
            if current is None:
                raise OrbiError("request_not_found", "Request disappeared unexpectedly.", 500)
            if current.status == "COMPLETED" and current.result is not None:
                return current.result
            if current.status in {"FAILED_FINAL", "CANCELLED", "EXPIRED"}:
                raise OrbiError(
                    "inference_failed", "The inference request could not be completed.", 503
                )
        await asyncio.sleep(0.25)

    raise OrbiError(
        "inference_timeout",
        f"Inference did not complete within the configured timeout. Request ID: {request_id}",
        504,
    )
