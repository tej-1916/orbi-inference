"""Explicitly opted-in tiny Gemma adapter smoke test."""

import os
from uuid import uuid4

import pytest

from orbi_node.config import NodeSettings
from orbi_node.runtimes.gemma_transformers import GemmaTransformersRuntime
from orbi_node.schemas import InferenceRequest


@pytest.mark.model_adapter
@pytest.mark.skipif(
    os.getenv("ORBI_RUN_TINY_MODEL_ADAPTER") != "1",
    reason="set ORBI_RUN_TINY_MODEL_ADAPTER=1 to download and execute a tiny model",
)
async def test_opt_in_tiny_gemma_adapter() -> None:
    model_id = os.getenv("ORBI_TINY_MODEL_ID", "tiny-random/gemma-2")
    settings = NodeSettings(
        core_url="http://127.0.0.1:8000",
        name="tiny-model-test",
        provider_type="local",
        enrollment_id="LookupId1234",
        enrollment_secret="s" * 43,
        supported_models=[model_id],
        runtime="gemma_transformers",
        model_id=model_id,
        model_revision=os.getenv("ORBI_TINY_MODEL_REVISION"),
        max_input_tokens=128,
        max_output_tokens=4,
        device="cpu",
        dtype="float32",
        quantization="none",
        trust_remote_code=False,
    )
    runtime = GemmaTransformersRuntime(settings)
    try:
        await runtime.load()
        result = await runtime.generate(
            InferenceRequest(
                id=uuid4(),
                model=model_id,
                payload={
                    "messages": [{"role": "user", "content": "Reply with one word."}],
                    "max_tokens": 4,
                },
            )
        )
        assert 0 <= result.output_tokens <= 4
    finally:
        await runtime.close()
