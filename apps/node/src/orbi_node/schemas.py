"""Validated gateway and runtime data contracts."""

from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class WorkerToken(BaseModel):
    worker_id: UUID
    access_token: str = Field(min_length=1)
    token_type: Literal["bearer"] = "bearer"  # noqa: S105
    expires_in: int = Field(gt=0)


class InferenceRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: UUID
    model: str = Field(min_length=1, max_length=256)
    payload: dict[str, Any]
    retry_count: int = Field(default=0, ge=0)
    lease_expires: str | None = None


class InferenceResult(BaseModel):
    request_id: UUID
    result: dict[str, Any]
    input_tokens: int = Field(ge=0)
    output_tokens: int = Field(ge=0)
    latency_ms: int = Field(ge=0)


class WorkerCapabilities(BaseModel):
    hostname_hash: str
    architecture: str
    operating_system: str
    cpu_count: int = Field(ge=1)
    memory_bytes: int | None = Field(default=None, ge=0)
    text_generation: bool = True
    max_concurrency: Literal[1] = 1
