"""Local Gemma adapter tests using an in-memory fake backend."""

from contextlib import nullcontext
from types import SimpleNamespace
from typing import Any
from uuid import uuid4

import pytest

from orbi_node.config import NodeSettings
from orbi_node.errors import NodeError
from orbi_node.runtimes.gemma_transformers import GemmaTransformersRuntime
from orbi_node.schemas import InferenceRequest


class FakeCudaOOM(Exception):
    pass


class FakeTensor:
    def __init__(self, token_count: int) -> None:
        self.token_count = token_count
        self.shape = (1, token_count)
        self.moved_to: object | None = None

    def to(self, device: object) -> "FakeTensor":
        self.moved_to = device
        return self

    def __getitem__(self, key: object) -> "FakeTensor":
        if not isinstance(key, tuple) or len(key) != 2:
            raise AssertionError("unexpected fake tensor index")
        token_slice = key[1]
        if not isinstance(token_slice, slice):
            raise AssertionError("expected token slice")
        start = token_slice.start or 0
        return FakeTensor(max(0, self.token_count - start))


class FakeCuda:
    OutOfMemoryError = FakeCudaOOM

    def __init__(self, *, available: bool = False, free_bytes: int = 1024**3) -> None:
        self._available = available
        self._free_bytes = free_bytes
        self.cache_cleared = False

    def is_available(self) -> bool:
        return self._available

    def mem_get_info(self) -> tuple[int, int]:
        return self._free_bytes, self._free_bytes * 2

    def empty_cache(self) -> None:
        self.cache_cleared = True


class FakeTokenizer:
    def __init__(self, *, input_tokens: int = 3, response: str = "private response") -> None:
        self.input_tokens = input_tokens
        self.response = response
        self.messages: list[dict[str, str]] | None = None

    def apply_chat_template(
        self,
        messages: list[dict[str, str]],
        **options: object,
    ) -> dict[str, FakeTensor]:
        self.messages = messages
        assert options == {
            "tokenize": True,
            "add_generation_prompt": True,
            "return_dict": True,
            "return_tensors": "pt",
        }
        return {
            "input_ids": FakeTensor(self.input_tokens),
            "attention_mask": FakeTensor(self.input_tokens),
        }

    def decode(self, _tokens: FakeTensor, *, skip_special_tokens: bool) -> str:
        assert skip_special_tokens is True
        return self.response


class FakeModel:
    def __init__(self, *, output_tokens: int = 2, failure: Exception | None = None) -> None:
        self.device = "cpu"
        self.output_tokens = output_tokens
        self.failure = failure
        self.evaluating = False
        self.generate_options: dict[str, object] | None = None

    def eval(self) -> None:
        self.evaluating = True

    def generate(self, **options: object) -> FakeTensor:
        self.generate_options = options
        if self.failure is not None:
            raise self.failure
        input_ids = options["input_ids"]
        assert isinstance(input_ids, FakeTensor)
        return FakeTensor(input_ids.token_count + self.output_tokens)


class FakeLoader:
    def __init__(self, value: object, events: list[str], event: str) -> None:
        self.value = value
        self.events = events
        self.event = event
        self.calls: list[tuple[str | None, dict[str, Any]]] = []

    def from_pretrained(self, model_id: str | None, **options: Any) -> object:
        self.events.append(self.event)
        self.calls.append((model_id, options))
        return self.value


def fake_torch(*, cuda: FakeCuda | None = None) -> SimpleNamespace:
    return SimpleNamespace(
        float32="float32-dtype",
        float16="float16-dtype",
        bfloat16="bfloat16-dtype",
        cuda=cuda or FakeCuda(),
        OutOfMemoryError=FakeCudaOOM,
        inference_mode=nullcontext,
    )


def gemma_settings(make_settings: Any, **overrides: object) -> NodeSettings:
    values: dict[str, object] = {
        "runtime": "gemma_transformers",
        "model_id": "google/gemma-2-2b-it",
        "max_input_tokens": 8,
        "max_output_tokens": 4,
    }
    values.update(overrides)
    return make_settings(**values)


def assigned_request(*, max_tokens: int = 2) -> InferenceRequest:
    return InferenceRequest(
        id=uuid4(),
        model="google/gemma-2-2b-it",
        payload={
            "messages": [{"role": "user", "content": "private prompt"}],
            "max_tokens": max_tokens,
        },
    )


def loaded_runtime(
    settings: NodeSettings,
    *,
    tokenizer: FakeTokenizer | None = None,
    model: FakeModel | None = None,
    torch: SimpleNamespace | None = None,
) -> GemmaTransformersRuntime:
    runtime = GemmaTransformersRuntime(settings)
    runtime._tokenizer = tokenizer or FakeTokenizer()
    runtime._model = model or FakeModel()
    runtime._torch = torch or fake_torch()
    return runtime


def test_cpu_load_runs_memory_preflight_and_disables_remote_code(
    make_settings: Any,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    settings = gemma_settings(make_settings, model_revision="a" * 40)
    tokenizer = FakeTokenizer()
    model = FakeModel()
    events: list[str] = []
    tokenizer_loader = FakeLoader(tokenizer, events, "tokenizer")
    model_loader = FakeLoader(model, events, "model")
    transformers = SimpleNamespace(
        AutoTokenizer=tokenizer_loader,
        AutoModelForCausalLM=model_loader,
    )
    runtime = GemmaTransformersRuntime(settings)
    monkeypatch.setattr(runtime, "_import_dependencies", lambda: (fake_torch(), transformers))
    monkeypatch.setattr(runtime, "_memory_preflight", lambda _torch: events.append("preflight"))

    runtime._load_sync()

    assert events == ["preflight", "tokenizer", "model"]
    assert runtime.loaded is True
    assert model.evaluating is True
    for _model_id, options in tokenizer_loader.calls + model_loader.calls:
        assert options["trust_remote_code"] is False
        assert options["revision"] == "a" * 40
    assert model_loader.calls[0][1]["device_map"] == {"": "cpu"}
    assert model_loader.calls[0][1]["dtype"] == "float32-dtype"


async def test_generation_enforces_chat_template_and_output_limit(
    make_settings: Any,
) -> None:
    settings = gemma_settings(make_settings)
    tokenizer = FakeTokenizer()
    model = FakeModel(output_tokens=2)
    runtime = loaded_runtime(settings, tokenizer=tokenizer, model=model)

    result = await runtime.generate(assigned_request(max_tokens=2))

    assert result.input_tokens == 3
    assert result.output_tokens == 2
    assert result.result["choices"][0]["message"]["content"] == "private response"
    assert tokenizer.messages == [{"role": "user", "content": "private prompt"}]
    assert model.generate_options is not None
    assert model.generate_options["max_new_tokens"] == 2
    assert model.generate_options["do_sample"] is False


async def test_input_token_limit_is_enforced(make_settings: Any) -> None:
    settings = gemma_settings(make_settings, max_input_tokens=2)
    runtime = loaded_runtime(settings, tokenizer=FakeTokenizer(input_tokens=3))
    with pytest.raises(NodeError) as error:
        await runtime.generate(assigned_request())
    assert error.value.code == "input_token_limit_exceeded"


async def test_output_token_limit_is_enforced_before_generation(make_settings: Any) -> None:
    settings = gemma_settings(make_settings, max_output_tokens=2)
    runtime = loaded_runtime(settings)
    with pytest.raises(NodeError) as error:
        await runtime.generate(assigned_request(max_tokens=3))
    assert error.value.code == "output_token_limit_exceeded"


async def test_cuda_oom_is_converted_to_controlled_error(make_settings: Any) -> None:
    settings = gemma_settings(
        make_settings,
        device="cuda",
        dtype="float16",
    )
    torch = fake_torch(cuda=FakeCuda(available=True))
    runtime = loaded_runtime(
        settings,
        model=FakeModel(failure=FakeCudaOOM("private allocator state")),
        torch=torch,
    )
    with pytest.raises(NodeError) as error:
        await runtime.generate(assigned_request())
    assert error.value.code == "cuda_out_of_memory"
    assert "private allocator state" not in error.value.safe_message


def test_cuda_preflight_rejects_unavailable_device(make_settings: Any) -> None:
    settings = gemma_settings(make_settings, device="cuda", dtype="float16")
    runtime = GemmaTransformersRuntime(settings)
    with pytest.raises(NodeError) as error:
        runtime._memory_preflight(fake_torch(cuda=FakeCuda(available=False)))
    assert error.value.code == "cuda_unavailable"


@pytest.mark.parametrize(
    ("available_bytes", "expected_code"),
    [
        (None, "memory_preflight_unavailable"),
        (128 * 1024 * 1024, "insufficient_model_memory"),
    ],
)
def test_cpu_preflight_fails_closed(
    make_settings: Any,
    monkeypatch: pytest.MonkeyPatch,
    available_bytes: int | None,
    expected_code: str,
) -> None:
    settings = gemma_settings(make_settings)
    runtime = GemmaTransformersRuntime(settings)
    monkeypatch.setattr(
        "orbi_node.runtimes.gemma_transformers._available_cpu_memory",
        lambda: available_bytes,
    )
    with pytest.raises(NodeError) as error:
        runtime._memory_preflight(fake_torch())
    assert error.value.code == expected_code


async def test_close_unloads_model_and_clears_cuda_cache(make_settings: Any) -> None:
    settings = gemma_settings(make_settings, device="cuda", dtype="float16")
    cuda = FakeCuda(available=True)
    runtime = loaded_runtime(settings, torch=fake_torch(cuda=cuda))
    await runtime.close()
    assert runtime.loaded is False
    assert runtime._torch is None
    assert cuda.cache_cleared is True
