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
    assert settings.runtime == "mock"
    assert settings.trust_remote_code is False


@pytest.mark.parametrize(
    "model_id",
    [
        "google/not-the-supported-family",
        "../local/gemma",
        "https://example.test/gemma",
        "google/gemma--2b",
        "google/gemma.git",
    ],
)
def test_invalid_model_ids_are_rejected(
    make_settings: object,
    model_id: str,
) -> None:
    with pytest.raises(ValidationError, match="valid Gemma Hub repository ID"):
        make_settings(  # type: ignore[operator]
            runtime="gemma_transformers",
            model_id=model_id,
        )


def test_remote_model_code_cannot_be_enabled(make_settings: object) -> None:
    with pytest.raises(ValidationError):
        make_settings(trust_remote_code=True)  # type: ignore[operator]


@pytest.mark.parametrize(
    ("overrides", "message"),
    [
        ({"device": "cpu", "dtype": "float16"}, "CPU runtime requires float32"),
        ({"device": "cpu", "quantization": "4bit"}, "quantization requires the CUDA"),
        (
            {"device": "cuda", "dtype": "float32", "quantization": "8bit"},
            "quantization requires float16 or bfloat16",
        ),
    ],
)
def test_invalid_device_dtype_and_quantization_combinations_are_rejected(
    make_settings: object,
    overrides: dict[str, str],
    message: str,
) -> None:
    with pytest.raises(ValidationError, match=message):
        make_settings(**overrides)  # type: ignore[operator]


def test_cpu_float32_without_quantization_is_valid(make_settings: object) -> None:
    settings = make_settings(  # type: ignore[operator]
        runtime="gemma_transformers",
        model_id="google/gemma-2-2b-it",
        device="cpu",
        dtype="float32",
        quantization="none",
    )
    assert settings.device == "cpu"


def test_model_revision_must_be_an_immutable_commit(make_settings: object) -> None:
    with pytest.raises(ValidationError, match="pinned 40-character commit hash"):
        make_settings(model_revision="main")  # type: ignore[operator]
    revision = "a" * 40
    assert make_settings(model_revision=revision).model_revision == revision  # type: ignore[operator]
