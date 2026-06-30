"""Structured node logging with defense-in-depth secret and content redaction."""

import logging
import re
from collections.abc import Mapping
from typing import Any

import structlog

_SENSITIVE_KEYS = {
    "authorization",
    "enrollment_secret",
    "enrollment_token",
    "access_token",
    "worker_jwt",
    "prompt",
    "messages",
    "generated_output",
    "hf_token",
    "huggingface_token",
    "response_text",
    "token",
}
_ORBI_CREDENTIAL = re.compile(r"orbi_(?:node|live|test|admin)_v1_[A-Za-z0-9_-]+")
_BEARER = re.compile(r"(?i)\bBearer\s+[A-Za-z0-9._~+/-]+=*")
_JWT = re.compile(r"\beyJ[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\b")


def _redact_value(value: Any, key: str | None = None) -> Any:
    if key is not None and key.lower() in _SENSITIVE_KEYS:
        return "[REDACTED]"
    if isinstance(value, Mapping):
        return {item_key: _redact_value(item, str(item_key)) for item_key, item in value.items()}
    if isinstance(value, list):
        return [_redact_value(item) for item in value]
    if isinstance(value, tuple):
        return tuple(_redact_value(item) for item in value)
    if isinstance(value, str):
        value = _ORBI_CREDENTIAL.sub("[REDACTED_ORBI_TOKEN]", value)
        value = _BEARER.sub("Bearer [REDACTED]", value)
        return _JWT.sub("[REDACTED_JWT]", value)
    return value


def redact_secrets(
    _logger: object, _method_name: str, event_dict: dict[str, Any]
) -> dict[str, Any]:
    """Redact credentials, authorization values, prompts, and generated content."""
    return {key: _redact_value(value, key) for key, value in event_dict.items()}


def configure_logging(level: str) -> None:
    """Configure JSON logs without request or response body rendering."""
    logging.basicConfig(level=level.upper(), format="%(message)s")
    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso", utc=True),
            redact_secrets,
            structlog.processors.JSONRenderer(),
        ],
        wrapper_class=structlog.make_filtering_bound_logger(
            logging.getLevelNamesMapping()[level.upper()]
        ),
        cache_logger_on_first_use=True,
    )
