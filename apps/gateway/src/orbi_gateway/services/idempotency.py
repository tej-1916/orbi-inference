"""Idempotency validation helpers; PostgreSQL uniqueness remains the source of truth."""

import re

_IDEMPOTENCY_RE = re.compile(r"^[A-Za-z0-9._:-]{8,128}$")


def validate_idempotency_key(value: str | None) -> str | None:
    """Validate a client idempotency key without silently normalising it."""
    if value is None:
        return None
    if _IDEMPOTENCY_RE.fullmatch(value) is None:
        raise ValueError("Idempotency-Key must be 8-128 URL-safe visible characters")
    return value
