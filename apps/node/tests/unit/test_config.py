"""Node configuration validation tests."""

import httpx
import pytest
from pydantic import ValidationError

from orbi_node.config import NodeSettings


def test_invalid_configuration_fails_before_network_access(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    network_constructed = False

    def forbidden_client(*args: object, **kwargs: object) -> None:
        nonlocal network_constructed
        network_constructed = True

    monkeypatch.setattr(httpx, "AsyncClient", forbidden_client)
    with pytest.raises(ValidationError):
        NodeSettings(
            core_url="not-a-url",
            name="node",
            provider_type="local",
            enrollment_id="short",
            enrollment_secret="bad",  # noqa: S106
            supported_models=[],
        )
    assert network_constructed is False


def test_all_environment_settings_use_node_prefix(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    values = {
        "CORE_URL": "https://ignored.example",
        "ORBI_NODE_CORE_URL": "https://core.example",
        "ORBI_NODE_NAME": "node",
        "ORBI_NODE_PROVIDER_TYPE": "local",
        "ORBI_NODE_ENROLLMENT_ID": "LookupId1234",
        "ORBI_NODE_ENROLLMENT_SECRET": "s" * 43,
        "ORBI_NODE_SUPPORTED_MODELS": "one/model,two/model",
        "ORBI_NODE_HEARTBEAT_INTERVAL_SECONDS": "10",
        "ORBI_NODE_POLL_INTERVAL_SECONDS": "1",
        "ORBI_NODE_HTTP_TIMEOUT_SECONDS": "2",
        "ORBI_NODE_LOG_LEVEL": "INFO",
    }
    for key, value in values.items():
        monkeypatch.setenv(key, value)
    settings = NodeSettings()  # type: ignore[call-arg]
    assert str(settings.core_url) == "https://core.example/"
    assert settings.supported_models == ["one/model", "two/model"]
