"""Shared inference runtime contract."""

from typing import Protocol

from orbi_node.schemas import InferenceRequest, InferenceResult


class InferenceRuntime(Protocol):
    """Lifecycle required by the single-flight worker."""

    async def load(self) -> None: ...

    async def generate(self, request: InferenceRequest) -> InferenceResult: ...

    async def close(self) -> None: ...
