"""Centralised, validated ORBI configuration; no module may read os.environ directly."""

from functools import lru_cache
from pathlib import Path

from pydantic import Field, SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Runtime settings loaded from environment variables or a local uncommitted `.env`."""

    model_config = SettingsConfigDict(
        env_prefix="ORBI_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    environment: str = "development"
    log_level: str = "INFO"
    database_url: str
    redis_url: str
    api_key_pepper: SecretStr
    worker_enrollment_pepper: SecretStr
    admin_token_hash: SecretStr
    admin_token_pepper: SecretStr
    jwt_private_key_path: Path
    jwt_public_key_path: Path
    jwt_issuer: str = "orbi-core"
    jwt_audience: str = "orbi-worker"
    worker_token_ttl_seconds: int = Field(default=3600, ge=300, le=86400)
    rate_limit_rpm_default: int = Field(default=60, ge=1, le=100000)
    max_request_body_bytes: int = Field(default=1_048_576, ge=1024, le=16_777_216)
    request_wait_timeout_seconds: int = Field(default=60, ge=1, le=600)
    worker_lease_seconds: int = Field(default=120, ge=30, le=1800)
    lease_recovery_interval_seconds: int = Field(default=30, ge=5, le=300)
    circuit_failure_threshold: int = Field(default=5, ge=1, le=100)
    circuit_cooldown_seconds: int = Field(default=120, ge=10, le=3600)

    @field_validator("api_key_pepper", "worker_enrollment_pepper", "admin_token_pepper")
    @classmethod
    def validate_secret_length(cls, value: SecretStr) -> SecretStr:
        """Reject weak placeholder secrets before the application starts."""
        raw = value.get_secret_value()
        if len(raw.encode()) < 32 or raw.startswith("replace-"):
            raise ValueError("security peppers must contain at least 32 non-placeholder bytes")
        return value


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return one immutable settings object per process."""
    return Settings()  # type: ignore[call-arg]
