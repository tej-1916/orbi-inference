"""Shared node test fixtures."""

from collections.abc import Callable

import pytest

from orbi_node.config import NodeSettings


@pytest.fixture
def make_settings() -> Callable[..., NodeSettings]:
    def factory(**overrides: object) -> NodeSettings:
        values: dict[str, object] = {
            "core_url": "https://core.example.test",
            "name": "test-node",
            "provider_type": "local",
            "enrollment_id": "LookupId1234",
            "enrollment_secret": "s" * 43,
            "supported_models": ["test/model"],
            "heartbeat_interval_seconds": 1,
            "poll_interval_seconds": 0.01,
            "http_timeout_seconds": 2,
            "max_http_retries": 2,
            "retry_base_seconds": 0.1,
            "retry_max_seconds": 5,
            "jwt_renewal_margin_seconds": 10,
        }
        values.update(overrides)
        return NodeSettings(**values)  # type: ignore[arg-type]

    return factory
