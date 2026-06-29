"""Idempotency-key validation unit tests."""

import pytest

from orbi_gateway.services.idempotency import validate_idempotency_key


def test_idempotency_accepts_uuid_like_value() -> None:
    value = "f4b71f9a-5690-44f0-802f-3048468e9080"
    assert validate_idempotency_key(value) == value


def test_idempotency_rejects_short_or_unsafe_value() -> None:
    with pytest.raises(ValueError):
        validate_idempotency_key("short")
    with pytest.raises(ValueError):
        validate_idempotency_key("invalid value with spaces")
