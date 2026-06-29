"""Structured logging configuration with credential redaction."""

import logging
import re
from collections.abc import MutableMapping
from typing import Any

import structlog

_TOKEN_PATTERN = re.compile(r"orbi_(?:live|test|node|admin)_v1_[A-Za-z0-9_-]+(?:_[A-Za-z0-9_-]+)?")


def redact_secrets(
    _: Any, __: str, event_dict: MutableMapping[str, Any]
) -> MutableMapping[str, Any]:
    """Redact ORBI credential-shaped values recursively from log events."""

    def scrub(value: Any) -> Any:
        if isinstance(value, str):
            return _TOKEN_PATTERN.sub("[REDACTED_ORBI_TOKEN]", value)
        if isinstance(value, dict):
            return {key: scrub(item) for key, item in value.items()}
        if isinstance(value, list):
            return [scrub(item) for item in value]
        return value

    return {key: scrub(value) for key, value in event_dict.items()}


def configure_logging(level: str) -> None:
    """Configure JSON logs for the gateway process."""
    logging.basicConfig(level=level.upper(), format="%(message)s")
    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso", utc=True),
            redact_secrets,
            structlog.processors.JSONRenderer(),
        ],
        wrapper_class=structlog.make_filtering_bound_logger(logging.getLevelName(level.upper())),
        logger_factory=structlog.stdlib.LoggerFactory(),
        cache_logger_on_first_use=True,
    )
