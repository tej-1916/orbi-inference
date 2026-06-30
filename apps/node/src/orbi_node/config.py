"""Typed node configuration loaded before any network client is created."""

import re
from functools import lru_cache
from pathlib import Path
from typing import Annotated, Literal

from pydantic import (
    AnyHttpUrl,
    BeforeValidator,
    Field,
    SecretStr,
    field_validator,
    model_validator,
)
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict


def _parse_models(value: object) -> object:
    if isinstance(value, str):
        return [item.strip() for item in value.split(",") if item.strip()]
    return value


_MODEL_ID = re.compile(
    r"^(?=.{3,96}$)[A-Za-z0-9][A-Za-z0-9._-]*/[A-Za-z0-9][A-Za-z0-9._-]*$"
)
_PINNED_REVISION = re.compile(r"^[0-9a-fA-F]{40}$")


class NodeSettings(BaseSettings):
    """Configuration exclusively sourced from ``ORBI_NODE_`` variables."""

    model_config = SettingsConfigDict(
        env_prefix="ORBI_NODE_",
        env_file=None,
        extra="ignore",
        case_sensitive=False,
    )

    core_url: AnyHttpUrl
    name: str = Field(min_length=1, max_length=128)
    provider_type: Literal["local", "docker", "dedicated", "colab", "kaggle"]
    enrollment_id: str = Field(min_length=12, max_length=12, pattern=r"^[A-Za-z0-9_-]+$")
    enrollment_secret: SecretStr
    supported_models: Annotated[list[str], NoDecode, BeforeValidator(_parse_models)] = Field(
        min_length=1, max_length=128
    )
    heartbeat_interval_seconds: float = Field(default=30.0, gt=0, le=300)
    poll_interval_seconds: float = Field(default=1.0, gt=0, le=60)
    http_timeout_seconds: float = Field(default=10.0, gt=0, le=120)
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR"] = "INFO"
    runtime: Literal["mock", "gemma_transformers"] = "mock"
    model_id: str | None = None
    model_revision: str | None = None
    model_cache_dir: Path | None = None
    max_input_tokens: int = Field(default=4096, ge=1, le=131_072)
    max_output_tokens: int = Field(default=512, ge=1, le=8192)
    device: Literal["cpu", "cuda"] = "cpu"
    dtype: Literal["float32", "float16", "bfloat16"] = "float32"
    quantization: Literal["none", "8bit", "4bit"] = "none"
    trust_remote_code: Literal[False] = False
    max_http_retries: int = Field(default=3, ge=0, le=10)
    retry_base_seconds: float = Field(default=0.25, gt=0, le=30)
    retry_max_seconds: float = Field(default=10.0, gt=0, le=300)
    jwt_renewal_margin_seconds: float = Field(default=60.0, ge=0, le=3600)

    @field_validator("enrollment_secret")
    @classmethod
    def validate_enrollment_secret(cls, value: SecretStr) -> SecretStr:
        secret = value.get_secret_value()
        if len(secret) != 43 or any(character not in _TOKEN_CHARS for character in secret):
            raise ValueError("enrollment secret must be a 43-character base64url value")
        return value

    @field_validator("supported_models")
    @classmethod
    def validate_models(cls, value: list[str]) -> list[str]:
        if any(not model or len(model) > 256 for model in value):
            raise ValueError("supported model IDs must contain 1 to 256 characters")
        return list(dict.fromkeys(value))

    @field_validator("model_id")
    @classmethod
    def validate_model_id(cls, value: str | None) -> str | None:
        if value is None:
            return None
        if (
            not _MODEL_ID.fullmatch(value)
            or ".." in value
            or "--" in value
            or value.endswith(".git")
            or "gemma" not in value.rsplit("/", 1)[1].lower()
        ):
            raise ValueError("model ID must be a valid Gemma Hub repository ID")
        return value

    @field_validator("model_revision")
    @classmethod
    def validate_model_revision(cls, value: str | None) -> str | None:
        if value is not None and not _PINNED_REVISION.fullmatch(value):
            raise ValueError("model revision must be a pinned 40-character commit hash")
        return value

    @field_validator("model_cache_dir")
    @classmethod
    def validate_model_cache_dir(cls, value: Path | None) -> Path | None:
        if value is not None and not value.is_absolute():
            raise ValueError("model cache directory must be an absolute path")
        return value

    @model_validator(mode="after")
    def validate_runtime_policy(self) -> "NodeSettings":
        if self.runtime == "gemma_transformers" and self.model_id is None:
            raise ValueError("model ID is required for the Gemma runtime")
        if self.device == "cpu" and self.dtype != "float32":
            raise ValueError("CPU runtime requires float32 dtype")
        if self.device == "cpu" and self.quantization != "none":
            raise ValueError("quantization requires the CUDA device")
        if self.quantization != "none" and self.dtype == "float32":
            raise ValueError("quantization requires float16 or bfloat16 dtype")
        return self

    @property
    def enrollment_token(self) -> str:
        """Assemble the gateway credential only at the enrollment boundary."""
        return (
            f"orbi_node_v1_{self.enrollment_id}_"
            f"{self.enrollment_secret.get_secret_value()}"
        )


_TOKEN_CHARS = frozenset(
    "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789-_"
)


@lru_cache
def get_settings() -> NodeSettings:
    """Validate all settings before application construction continues."""
    return NodeSettings()  # type: ignore[call-arg]
