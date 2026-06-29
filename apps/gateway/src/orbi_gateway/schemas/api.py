"""Public and internal API schemas; these models never expose credential hashes."""

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field


class ChatMessage(BaseModel):
    role: Literal["system", "user", "assistant"]
    content: str = Field(min_length=1, max_length=100_000)


class ChatCompletionRequest(BaseModel):
    model: str = Field(min_length=1, max_length=64)
    messages: list[ChatMessage] = Field(min_length=1, max_length=256)
    stream: bool = False
    max_tokens: int = Field(default=512, ge=1, le=4096)
    temperature: float = Field(default=0.7, ge=0.0, le=2.0)


class APIKeyCreateRequest(BaseModel):
    project_id: UUID
    environment: Literal["live", "test"]
    name: str | None = Field(default=None, max_length=128)
    scopes: list[str] = Field(
        default_factory=lambda: ["chat", "models:read", "usage:read"], max_length=32
    )
    expires_at: datetime | None = None
    rpm_limit: int = Field(default=60, ge=1, le=100_000)
    daily_req_limit: int = Field(default=1000, ge=1, le=10_000_000)


class APIKeyCreatedResponse(BaseModel):
    id: UUID
    key: str
    display_prefix: str
    warning: str = "Store this key now. ORBI will never show it again."


class WorkerEnrollmentCreateRequest(BaseModel):
    expires_in_seconds: int = Field(default=900, ge=60, le=86400)


class WorkerEnrollmentCreatedResponse(BaseModel):
    enrollment_token: str
    expires_at: datetime
    warning: str = "Store this one-time token securely. It will not be shown again."


class WorkerRegisterRequest(BaseModel):
    enrollment_token: str = Field(min_length=32, max_length=512)
    provider_type: Literal["colab", "kaggle", "local", "docker", "dedicated"]
    name: str = Field(min_length=1, max_length=128)
    supported_models: list[str] = Field(default_factory=list, max_length=128)
    capabilities: dict[str, object] = Field(default_factory=dict)


class WorkerTokenResponse(BaseModel):
    worker_id: UUID
    access_token: str
    token_type: Literal["bearer"] = "bearer"  # noqa: S105
    expires_in: int


class WorkerHeartbeatRequest(BaseModel):
    status: Literal["ONLINE", "DRAINING"]
    current_queue_depth: int = Field(ge=0, le=100_000)
    capabilities: dict[str, object] = Field(default_factory=dict)


class WorkerResultRequest(BaseModel):
    request_id: UUID
    result: dict[str, object]
    input_tokens: int = Field(ge=0)
    output_tokens: int = Field(ge=0)
    latency_ms: int = Field(ge=0)


class WorkerErrorRequest(BaseModel):
    request_id: UUID
    retryable: bool = True
    error_code: str = Field(min_length=1, max_length=64, pattern=r"^[a-z0-9_]+$")
    message: str = Field(min_length=1, max_length=512)


class ProjectCreateRequest(BaseModel):
    name: str = Field(min_length=1, max_length=128)
    slug: str = Field(min_length=3, max_length=64, pattern=r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
    owner_id: UUID
    daily_token_limit: int = Field(default=100_000, ge=1)
    monthly_token_limit: int = Field(default=1_000_000, ge=1)


class ProjectResponse(BaseModel):
    id: UUID
    name: str
    slug: str


class ModelAliasCreateRequest(BaseModel):
    alias: str = Field(min_length=1, max_length=64, pattern=r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
    display_name: str | None = Field(default=None, max_length=128)
    model_id: str = Field(min_length=1, max_length=256)
    min_vram_gb: float | None = Field(default=None, ge=0)
    required_capabilities: dict[str, object] = Field(default_factory=dict)
    supports_streaming: bool = True
    supports_tools: bool = False
    max_context_tokens: int = Field(default=4096, ge=128, le=2_000_000)


class ModelAliasResponse(BaseModel):
    alias: str
    model_id: str


class ErrorBody(BaseModel):
    code: str
    message: str


class ErrorResponse(BaseModel):
    error: ErrorBody
