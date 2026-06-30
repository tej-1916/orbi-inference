"""Inference runtime registry tests."""

from collections.abc import Callable

import pytest

from orbi_node.config import NodeSettings
from orbi_node.runtimes.mock import MockInferenceRuntime
from orbi_node.runtimes.registry import create_runtime


def test_mock_runtime_is_the_default(
    make_settings: Callable[..., NodeSettings],
) -> None:
    assert isinstance(create_runtime(make_settings()), MockInferenceRuntime)


def test_unsupported_runtime_is_rejected(
    make_settings: Callable[..., NodeSettings],
) -> None:
    settings = make_settings()
    object.__setattr__(settings, "runtime", "unsupported")
    with pytest.raises(ValueError, match="Unsupported node runtime"):
        create_runtime(settings)
