"""Create the ORBI Phase 1 control-plane schema."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0001_phase1"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "projects",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("name", sa.String(128), nullable=False),
        sa.Column("slug", sa.String(64), nullable=False, unique=True),
        sa.Column("owner_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("monthly_token_limit", sa.BigInteger(), nullable=False, server_default="1000000"),
        sa.Column("monthly_tokens_used", sa.BigInteger(), nullable=False, server_default="0"),
        sa.Column("daily_token_limit", sa.BigInteger(), nullable=False, server_default="100000"),
        sa.Column("daily_tokens_used", sa.BigInteger(), nullable=False, server_default="0"),
        sa.Column(
            "daily_usage_date", sa.Date(), nullable=False, server_default=sa.text("CURRENT_DATE")
        ),
        sa.Column(
            "monthly_usage_month",
            sa.Date(),
            nullable=False,
            server_default=sa.text("(date_trunc('month', CURRENT_DATE)::date)"),
        ),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
    )
    op.create_table(
        "api_keys",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "project_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("projects.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("key_id", sa.String(32), nullable=False, unique=True),
        sa.Column("display_prefix", sa.String(64), nullable=False),
        sa.Column("secret_hash", sa.Text(), nullable=False),
        sa.Column("environment", sa.String(8), nullable=False),
        sa.Column("name", sa.String(128)),
        sa.Column(
            "scopes",
            postgresql.ARRAY(sa.Text()),
            nullable=False,
            server_default="{chat,models:read,usage:read}",
        ),
        sa.Column("expires_at", sa.DateTime(timezone=True)),
        sa.Column("revoked_at", sa.DateTime(timezone=True)),
        sa.Column("last_used_at", sa.DateTime(timezone=True)),
        sa.Column("total_requests", sa.BigInteger(), nullable=False, server_default="0"),
        sa.Column("total_tokens", sa.BigInteger(), nullable=False, server_default="0"),
        sa.Column("rpm_limit", sa.Integer(), nullable=False, server_default="60"),
        sa.Column("daily_req_limit", sa.Integer(), nullable=False, server_default="1000"),
        sa.Column("daily_requests_used", sa.Integer(), nullable=False, server_default="0"),
        sa.Column(
            "daily_requests_date", sa.Date(), nullable=False, server_default=sa.text("CURRENT_DATE")
        ),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.CheckConstraint("environment IN ('live', 'test')", name="ck_api_keys_environment"),
    )
    op.create_table(
        "model_aliases",
        sa.Column("alias", sa.String(64), primary_key=True),
        sa.Column("display_name", sa.String(128)),
        sa.Column("model_id", sa.String(256), nullable=False),
        sa.Column("fallback_alias", sa.String(64), sa.ForeignKey("model_aliases.alias")),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("min_vram_gb", sa.Float()),
        sa.Column(
            "required_capabilities",
            postgresql.JSONB(),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column("supports_streaming", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("supports_tools", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("max_context_tokens", sa.Integer(), nullable=False, server_default="4096"),
    )
    op.create_table(
        "workers",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("provider_type", sa.String(32), nullable=False),
        sa.Column("name", sa.String(128), nullable=False),
        sa.Column("status", sa.String(32), nullable=False, server_default="OFFLINE"),
        sa.Column(
            "supported_models", postgresql.ARRAY(sa.Text()), nullable=False, server_default="{}"
        ),
        sa.Column(
            "capabilities",
            postgresql.JSONB(),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column("current_queue_depth", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("failure_count_1h", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("p95_latency_ms", sa.Float()),
        sa.Column("token_jti", sa.String(128)),
        sa.Column(
            "registered_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column("last_heartbeat", sa.DateTime(timezone=True)),
        sa.Column("revoked_at", sa.DateTime(timezone=True)),
    )
    op.create_table(
        "worker_enrollment_tokens",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("token_id", sa.String(32), nullable=False, unique=True),
        sa.Column("secret_hash", sa.Text(), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("consumed_at", sa.DateTime(timezone=True)),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
    )
    op.create_table(
        "orbi_requests",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("idempotency_key", sa.String(128)),
        sa.Column(
            "project_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("projects.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "api_key_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("api_keys.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("model_alias", sa.String(64), nullable=False),
        sa.Column("resolved_model", sa.String(256), nullable=False),
        sa.Column("payload", postgresql.JSONB(), nullable=False),
        sa.Column(
            "required_capabilities",
            postgresql.JSONB(),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column("priority", sa.SmallInteger(), nullable=False, server_default="5"),
        sa.Column("status", sa.String(32), nullable=False, server_default="QUEUED"),
        sa.Column(
            "assigned_to",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("workers.id", ondelete="SET NULL"),
        ),
        sa.Column("lease_expires", sa.DateTime(timezone=True)),
        sa.Column("retry_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("max_retries", sa.Integer(), nullable=False, server_default="3"),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True)),
        sa.Column("result", postgresql.JSONB()),
        sa.Column("error_detail", postgresql.JSONB()),
        sa.Column("input_tokens", sa.Integer()),
        sa.Column("output_tokens", sa.Integer()),
        sa.Column("reserved_tokens", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("budget_day", sa.Date(), nullable=False, server_default=sa.text("CURRENT_DATE")),
        sa.Column(
            "budget_month",
            sa.Date(),
            nullable=False,
            server_default=sa.text("(date_trunc('month', CURRENT_DATE)::date)"),
        ),
        sa.UniqueConstraint("api_key_id", "idempotency_key", name="uq_requests_key_idempotency"),
        sa.CheckConstraint("priority BETWEEN 1 AND 10", name="ck_requests_priority"),
    )
    op.create_index(
        "idx_requests_queue",
        "orbi_requests",
        ["priority", "created_at"],
        postgresql_where=sa.text("status = 'QUEUED'"),
    )
    op.create_index(
        "idx_requests_lease",
        "orbi_requests",
        ["lease_expires"],
        postgresql_where=sa.text("status IN ('ASSIGNED','STARTING','RUNNING')"),
    )
    op.create_table(
        "usage_records",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "request_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("orbi_requests.id", ondelete="RESTRICT"),
            nullable=False,
            unique=True,
        ),
        sa.Column(
            "project_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("projects.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "api_key_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("api_keys.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "worker_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("workers.id", ondelete="SET NULL"),
        ),
        sa.Column("provider_type", sa.String(32)),
        sa.Column("model_id", sa.String(256), nullable=False),
        sa.Column("input_tokens", sa.Integer(), nullable=False),
        sa.Column("output_tokens", sa.Integer(), nullable=False),
        sa.Column("latency_ms", sa.Integer()),
        sa.Column("cost_usd", sa.Numeric(12, 8), nullable=False, server_default="0"),
        sa.Column(
            "recorded_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
    )
    op.create_index("idx_usage_project_day", "usage_records", ["project_id", "recorded_at"])
    op.create_table(
        "incidents",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("type", sa.String(64), nullable=False),
        sa.Column("severity", sa.String(16), nullable=False),
        sa.Column(
            "worker_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("workers.id", ondelete="SET NULL"),
        ),
        sa.Column(
            "detail", postgresql.JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")
        ),
        sa.Column("resolved_at", sa.DateTime(timezone=True)),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.CheckConstraint(
            "severity IN ('info','warning','critical')", name="ck_incidents_severity"
        ),
    )


def downgrade() -> None:
    for table in [
        "incidents",
        "usage_records",
        "orbi_requests",
        "worker_enrollment_tokens",
        "workers",
        "model_aliases",
        "api_keys",
        "projects",
    ]:
        op.drop_table(table)
