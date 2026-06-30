"""Deterministic mock runtime tests."""

from uuid import uuid4

import pytest

from orbi_node.errors import NodeError
from orbi_node.runtimes.mock import MockInferenceRuntime
from orbi_node.schemas import InferenceRequest


def request() -> InferenceRequest:
    return InferenceRequest(
        id=uuid4(),
        model="test/model",
        payload={
            "messages": [{"role": "user", "content": "__import__('os').system('bad')"}],
            "max_tokens": 10,
        },
    )


async def test_mock_inference_is_deterministic_and_non_executing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr("os.system", lambda _command: pytest.fail("input was executed"))
    runtime = MockInferenceRuntime()
    await runtime.load()
    assigned = request()
    first = await runtime.generate(assigned)
    second = await runtime.generate(assigned)
    assert first.result == second.result
    assert first.input_tokens == second.input_tokens
    assert first.output_tokens == 5
    assert first.request_id == assigned.id


async def test_mock_runtime_supports_controlled_failure() -> None:
    failure = NodeError("controlled_failure", "Controlled failure.", retryable=False)
    runtime = MockInferenceRuntime(failure=failure)
    await runtime.load()
    with pytest.raises(NodeError, match="Controlled failure"):
        await runtime.generate(request())
