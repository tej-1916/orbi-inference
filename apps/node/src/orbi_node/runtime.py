"""Replaceable inference runtime and deterministic test implementation."""

import asyncio
import hashlib
import json
import time
from typing import Protocol

from orbi_node.errors import NodeError
from orbi_node.schemas import InferenceRequest, InferenceResult


class InferenceRuntime(Protocol):
    async def load(self) -> None: ...

    async def generate(self, request: InferenceRequest) -> InferenceResult: ...

    async def close(self) -> None: ...


class MockInferenceRuntime:
    """Deterministic, non-executing runtime with explicit test controls."""

    def __init__(
        self,
        *,
        delay_seconds: float = 0.0,
        failure: NodeError | None = None,
    ) -> None:
        self._delay = delay_seconds
        self._failure = failure
        self.loaded = False

    async def load(self) -> None:
        self.loaded = True

    async def generate(self, request: InferenceRequest) -> InferenceResult:
        if not self.loaded:
            raise NodeError("runtime_not_loaded", "Inference runtime is not loaded.")
        started = time.monotonic()
        if self._delay:
            await asyncio.sleep(self._delay)
        if self._failure is not None:
            raise self._failure

        canonical = json.dumps(
            {"model": request.model, "payload": request.payload},
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=True,
        )
        digest = hashlib.sha256(canonical.encode()).hexdigest()[:24]
        output = f"ORBI deterministic mock response {digest}"
        input_tokens = max(1, (len(canonical.encode()) + 3) // 4)
        output_tokens = len(output.split())
        result = {
            "id": f"orbi-{request.id}",
            "object": "chat.completion",
            "model": request.model,
            "choices": [
                {
                    "index": 0,
                    "message": {"role": "assistant", "content": output},
                    "finish_reason": "stop",
                }
            ],
            "usage": {
                "prompt_tokens": input_tokens,
                "completion_tokens": output_tokens,
                "total_tokens": input_tokens + output_tokens,
            },
        }
        return InferenceResult(
            request_id=request.id,
            result=result,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            latency_ms=max(0, int((time.monotonic() - started) * 1000)),
        )

    async def close(self) -> None:
        self.loaded = False
