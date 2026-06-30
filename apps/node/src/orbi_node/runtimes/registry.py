"""Runtime selection without model-specific worker logic."""

from collections.abc import Callable

from orbi_node.config import NodeSettings
from orbi_node.runtimes.base import InferenceRuntime
from orbi_node.runtimes.mock import MockInferenceRuntime

RuntimeFactory = Callable[[NodeSettings], InferenceRuntime]


def _mock_runtime(_settings: NodeSettings) -> InferenceRuntime:
    return MockInferenceRuntime()


_RUNTIME_FACTORIES: dict[str, RuntimeFactory] = {"mock": _mock_runtime}


def create_runtime(settings: NodeSettings) -> InferenceRuntime:
    """Construct the configured runtime or fail closed."""
    try:
        factory = _RUNTIME_FACTORIES[settings.runtime]
    except KeyError as exc:
        raise ValueError("Unsupported node runtime.") from exc
    return factory(settings)
