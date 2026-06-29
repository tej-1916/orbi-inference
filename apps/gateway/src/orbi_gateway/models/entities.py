"""Persisted ORBI Phase 1 entities; business logic belongs in services, not models."""

from datetime import date, datetime
from decimal import Decimal
from uuid import UUID, uuid4

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    Numeric,
    SmallInteger,
    String,
    Text,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import ARRAY, JSONB
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from orbi_gateway.models.base import Base


class Project(Base):
    __tablename__ = "projects"
    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    name: Mapped[str] = mapped_column(String(128))
    slug: Mapped[str] = mapped_column(String(64), unique=True)
    owner_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True))
    monthly_token_limit: Mapped[int] = mapped_column(BigInteger, default=1_000_000)
    monthly_tokens_used: Mapped[int] = mapped_column(BigInteger, default=0)
    daily_token_limit: Mapped[int] = mapped_column(BigInteger, default=100_000)
    daily_tokens_used: Mapped[int] = mapped_column(BigInteger, default=0)
    daily_usage_date: Mapped[date] = mapped_column(Date, server_default=func.current_date())
    monthly_usage_month: Mapped[date] = mapped_column(
        Date, server_default=text("(date_trunc('month', CURRENT_DATE)::date)")
    )
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class APIKey(Base):
    __tablename__ = "api_keys"
    __table_args__ = (CheckConstraint("environment IN ('live','test')"),)
    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    project_id: Mapped[UUID] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"))
    key_id: Mapped[str] = mapped_column(String(32), unique=True, index=True)
    display_prefix: Mapped[str] = mapped_column(String(64))
    secret_hash: Mapped[str] = mapped_column(Text)
    environment: Mapped[str] = mapped_column(String(8))
    name: Mapped[str | None] = mapped_column(String(128))
    scopes: Mapped[list[str]] = mapped_column(
        ARRAY(Text), default=lambda: ["chat", "models:read", "usage:read"]
    )
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    total_requests: Mapped[int] = mapped_column(BigInteger, default=0)
    total_tokens: Mapped[int] = mapped_column(BigInteger, default=0)
    rpm_limit: Mapped[int] = mapped_column(Integer, default=60)
    daily_req_limit: Mapped[int] = mapped_column(Integer, default=1000)
    daily_requests_used: Mapped[int] = mapped_column(Integer, default=0)
    daily_requests_date: Mapped[date] = mapped_column(Date, server_default=func.current_date())
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class ModelAlias(Base):
    __tablename__ = "model_aliases"
    alias: Mapped[str] = mapped_column(String(64), primary_key=True)
    display_name: Mapped[str | None] = mapped_column(String(128))
    model_id: Mapped[str] = mapped_column(String(256))
    fallback_alias: Mapped[str | None] = mapped_column(ForeignKey("model_aliases.alias"))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    min_vram_gb: Mapped[float | None] = mapped_column(Float)
    required_capabilities: Mapped[dict[str, object]] = mapped_column(JSONB, default=dict)
    supports_streaming: Mapped[bool] = mapped_column(Boolean, default=True)
    supports_tools: Mapped[bool] = mapped_column(Boolean, default=False)
    max_context_tokens: Mapped[int] = mapped_column(Integer, default=4096)


class Worker(Base):
    __tablename__ = "workers"
    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    provider_type: Mapped[str] = mapped_column(String(32))
    name: Mapped[str] = mapped_column(String(128))
    status: Mapped[str] = mapped_column(String(32), default="OFFLINE")
    supported_models: Mapped[list[str]] = mapped_column(ARRAY(Text), default=list)
    capabilities: Mapped[dict[str, object]] = mapped_column(JSONB, default=dict)
    current_queue_depth: Mapped[int] = mapped_column(Integer, default=0)
    failure_count_1h: Mapped[int] = mapped_column(Integer, default=0)
    p95_latency_ms: Mapped[float | None] = mapped_column(Float)
    token_jti: Mapped[str | None] = mapped_column(String(128))
    registered_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    last_heartbeat: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class WorkerEnrollmentToken(Base):
    __tablename__ = "worker_enrollment_tokens"
    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    token_id: Mapped[str] = mapped_column(String(32), unique=True, index=True)
    secret_hash: Mapped[str] = mapped_column(Text)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    consumed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class OrbiRequest(Base):
    __tablename__ = "orbi_requests"
    __table_args__ = (
        UniqueConstraint("api_key_id", "idempotency_key", name="uq_requests_key_idempotency"),
        CheckConstraint("priority BETWEEN 1 AND 10"),
    )
    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    idempotency_key: Mapped[str | None] = mapped_column(String(128))
    project_id: Mapped[UUID] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"))
    api_key_id: Mapped[UUID] = mapped_column(ForeignKey("api_keys.id", ondelete="RESTRICT"))
    model_alias: Mapped[str] = mapped_column(String(64))
    resolved_model: Mapped[str] = mapped_column(String(256))
    payload: Mapped[dict[str, object]] = mapped_column(JSONB)
    required_capabilities: Mapped[dict[str, object]] = mapped_column(JSONB, default=dict)
    priority: Mapped[int] = mapped_column(SmallInteger, default=5)
    status: Mapped[str] = mapped_column(String(32), default="QUEUED")
    assigned_to: Mapped[UUID | None] = mapped_column(ForeignKey("workers.id", ondelete="SET NULL"))
    lease_expires: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    retry_count: Mapped[int] = mapped_column(Integer, default=0)
    max_retries: Mapped[int] = mapped_column(Integer, default=3)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    result: Mapped[dict[str, object] | None] = mapped_column(JSONB)
    error_detail: Mapped[dict[str, object] | None] = mapped_column(JSONB)
    input_tokens: Mapped[int | None] = mapped_column(Integer)
    output_tokens: Mapped[int | None] = mapped_column(Integer)
    reserved_tokens: Mapped[int] = mapped_column(Integer, default=0)
    budget_day: Mapped[date] = mapped_column(Date, server_default=func.current_date())
    budget_month: Mapped[date] = mapped_column(
        Date, server_default=text("(date_trunc('month', CURRENT_DATE)::date)")
    )


class UsageRecord(Base):
    __tablename__ = "usage_records"
    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    request_id: Mapped[UUID] = mapped_column(
        ForeignKey("orbi_requests.id", ondelete="RESTRICT"), unique=True
    )
    project_id: Mapped[UUID] = mapped_column(ForeignKey("projects.id", ondelete="RESTRICT"))
    api_key_id: Mapped[UUID] = mapped_column(ForeignKey("api_keys.id", ondelete="RESTRICT"))
    worker_id: Mapped[UUID | None] = mapped_column(ForeignKey("workers.id", ondelete="SET NULL"))
    provider_type: Mapped[str | None] = mapped_column(String(32))
    model_id: Mapped[str] = mapped_column(String(256))
    input_tokens: Mapped[int] = mapped_column(Integer)
    output_tokens: Mapped[int] = mapped_column(Integer)
    latency_ms: Mapped[int | None] = mapped_column(Integer)
    cost_usd: Mapped[Decimal] = mapped_column(Numeric(12, 8), default=Decimal("0"))
    recorded_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class Incident(Base):
    __tablename__ = "incidents"
    __table_args__ = (CheckConstraint("severity IN ('info','warning','critical')"),)
    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    type: Mapped[str] = mapped_column(String(64))
    severity: Mapped[str] = mapped_column(String(16))
    worker_id: Mapped[UUID | None] = mapped_column(ForeignKey("workers.id", ondelete="SET NULL"))
    detail: Mapped[dict[str, object]] = mapped_column(JSONB, default=dict)
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
