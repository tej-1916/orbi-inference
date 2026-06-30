"""Optional local Gemma runtime backed by Transformers and PyTorch."""

import asyncio
import gc
import importlib
import os
import time
from types import ModuleType
from typing import Any

from orbi_node.config import NodeSettings
from orbi_node.errors import NodeError
from orbi_node.schemas import InferenceRequest, InferenceResult

_MINIMUM_CPU_FREE_BYTES = 256 * 1024 * 1024
_MINIMUM_CUDA_FREE_BYTES = 256 * 1024 * 1024
_ALLOWED_ROLES = frozenset({"system", "user", "assistant"})


def _available_cpu_memory() -> int | None:
    """Return currently available physical memory on POSIX systems."""
    try:
        page_size = os.sysconf("SC_PAGE_SIZE")
        available_pages = os.sysconf("SC_AVPHYS_PAGES")
    except (AttributeError, OSError, ValueError):
        return None
    return int(page_size) * int(available_pages)


class GemmaTransformersRuntime:
    """Single-model, single-flight local Gemma inference runtime."""

    def __init__(self, settings: NodeSettings) -> None:
        self._settings = settings
        self._torch: ModuleType | None = None
        self._tokenizer: Any = None
        self._model: Any = None

    @property
    def loaded(self) -> bool:
        return self._model is not None and self._tokenizer is not None

    async def load(self) -> None:
        if self.loaded:
            return
        await asyncio.to_thread(self._load_sync)

    def _load_sync(self) -> None:
        try:
            torch, transformers = self._import_dependencies()
            self._memory_preflight(torch)
            dtype = getattr(torch, self._settings.dtype)
            common_options: dict[str, Any] = {
                "cache_dir": (
                    str(self._settings.model_cache_dir)
                    if self._settings.model_cache_dir is not None
                    else None
                ),
                "revision": self._settings.model_revision,
                "trust_remote_code": False,
            }
            tokenizer = transformers.AutoTokenizer.from_pretrained(
                self._settings.model_id,
                **common_options,
            )
            model_options = {
                **common_options,
                "device_map": {"": 0 if self._settings.device == "cuda" else "cpu"},
                "dtype": dtype,
            }
            if self._settings.quantization != "none":
                model_options["quantization_config"] = self._quantization_config(
                    transformers, dtype
                )
            model = transformers.AutoModelForCausalLM.from_pretrained(
                self._settings.model_id,
                **model_options,
            )
            model.eval()
        except NodeError:
            raise
        except Exception as exc:
            if self._is_cuda_oom(exc, self._torch):
                raise self._cuda_oom_error() from None
            raise NodeError(
                "model_load_failed",
                "The configured local model could not be loaded.",
                retryable=False,
            ) from None
        self._torch = torch
        self._tokenizer = tokenizer
        self._model = model

    async def generate(self, request: InferenceRequest) -> InferenceResult:
        if not self.loaded or self._torch is None:
            raise NodeError("runtime_not_loaded", "Inference runtime is not loaded.")
        try:
            return await asyncio.to_thread(self._generate_sync, request)
        except NodeError:
            raise
        except Exception as exc:
            if self._is_cuda_oom(exc, self._torch):
                raise self._cuda_oom_error() from None
            raise NodeError(
                "inference_failed",
                "Local model inference failed.",
            ) from None

    def _generate_sync(self, request: InferenceRequest) -> InferenceResult:
        if request.model != self._settings.model_id:
            raise NodeError(
                "model_not_loaded",
                "The request model is not loaded by this node.",
                retryable=False,
            )
        messages, requested_output_tokens = self._validated_request(request)
        started = time.monotonic()
        encoded = self._tokenizer.apply_chat_template(
            messages,
            tokenize=True,
            add_generation_prompt=True,
            return_dict=True,
            return_tensors="pt",
        )
        input_ids = encoded["input_ids"]
        input_tokens = int(input_ids.shape[-1])
        if input_tokens > self._settings.max_input_tokens:
            raise NodeError(
                "input_token_limit_exceeded",
                "Input exceeds the configured token limit.",
                retryable=False,
            )
        model_device = self._model.device
        model_inputs = {
            key: value.to(model_device) if hasattr(value, "to") else value
            for key, value in encoded.items()
        }
        with self._torch.inference_mode():
            generated = self._model.generate(
                **model_inputs,
                max_new_tokens=requested_output_tokens,
                do_sample=False,
            )
        generated_tokens = generated[0, input_tokens:]
        output_tokens = int(generated_tokens.shape[-1])
        if output_tokens > self._settings.max_output_tokens:
            raise NodeError(
                "output_token_limit_exceeded",
                "Output exceeds the configured token limit.",
                retryable=False,
            )
        output = self._tokenizer.decode(generated_tokens, skip_special_tokens=True)
        return InferenceResult(
            request_id=request.id,
            result={
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
            },
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            latency_ms=max(0, int((time.monotonic() - started) * 1000)),
        )

    def _validated_request(
        self, request: InferenceRequest
    ) -> tuple[list[dict[str, str]], int]:
        messages = request.payload.get("messages")
        if not isinstance(messages, list) or not messages:
            raise NodeError(
                "invalid_inference_request",
                "A non-empty messages list is required.",
                retryable=False,
            )
        validated: list[dict[str, str]] = []
        for message in messages:
            if not isinstance(message, dict):
                raise NodeError(
                    "invalid_inference_request",
                    "Every message must contain a supported role and text content.",
                    retryable=False,
                )
            role = message.get("role")
            content = message.get("content")
            if role not in _ALLOWED_ROLES or not isinstance(content, str):
                raise NodeError(
                    "invalid_inference_request",
                    "Every message must contain a supported role and text content.",
                    retryable=False,
                )
            validated.append({"role": role, "content": content})
        requested = request.payload.get("max_tokens", self._settings.max_output_tokens)
        if isinstance(requested, bool) or not isinstance(requested, int) or requested < 1:
            raise NodeError(
                "invalid_output_token_limit",
                "The requested output token limit must be a positive integer.",
                retryable=False,
            )
        if requested > self._settings.max_output_tokens:
            raise NodeError(
                "output_token_limit_exceeded",
                "Requested output exceeds the configured token limit.",
                retryable=False,
            )
        return validated, requested

    def _memory_preflight(self, torch: ModuleType) -> None:
        if self._settings.device == "cuda":
            if not torch.cuda.is_available():
                raise NodeError(
                    "cuda_unavailable",
                    "CUDA was requested but is not available.",
                    retryable=False,
                )
            free_bytes, _total_bytes = torch.cuda.mem_get_info()
            if free_bytes < _MINIMUM_CUDA_FREE_BYTES:
                raise NodeError(
                    "insufficient_model_memory",
                    "Insufficient free CUDA memory for model loading.",
                    retryable=False,
                )
            return
        free_bytes = _available_cpu_memory()
        if free_bytes is None:
            raise NodeError(
                "memory_preflight_unavailable",
                "Available system memory could not be determined.",
                retryable=False,
            )
        if free_bytes < _MINIMUM_CPU_FREE_BYTES:
            raise NodeError(
                "insufficient_model_memory",
                "Insufficient free system memory for model loading.",
                retryable=False,
            )

    def _import_dependencies(self) -> tuple[ModuleType, ModuleType]:
        try:
            torch = importlib.import_module("torch")
            transformers = importlib.import_module("transformers")
        except ImportError:
            raise NodeError(
                "runtime_dependency_missing",
                "Install the optional Gemma runtime dependencies.",
                retryable=False,
            ) from None
        self._torch = torch
        return torch, transformers

    def _quantization_config(self, transformers: ModuleType, dtype: Any) -> Any:
        if self._settings.quantization == "4bit":
            return transformers.BitsAndBytesConfig(
                load_in_4bit=True,
                bnb_4bit_compute_dtype=dtype,
            )
        return transformers.BitsAndBytesConfig(load_in_8bit=True)

    @staticmethod
    def _is_cuda_oom(exc: Exception, torch: ModuleType | None) -> bool:
        if torch is None:
            return False
        oom_types = tuple(
            error_type
            for error_type in (
                getattr(torch, "OutOfMemoryError", None),
                getattr(getattr(torch, "cuda", None), "OutOfMemoryError", None),
            )
            if isinstance(error_type, type)
        )
        return bool(oom_types) and isinstance(exc, oom_types)

    @staticmethod
    def _cuda_oom_error() -> NodeError:
        return NodeError(
            "cuda_out_of_memory",
            "CUDA memory was exhausted during local inference.",
        )

    async def close(self) -> None:
        await asyncio.to_thread(self._close_sync)

    def _close_sync(self) -> None:
        model, tokenizer = self._model, self._tokenizer
        self._model = None
        self._tokenizer = None
        del model, tokenizer
        gc.collect()
        if self._torch is not None and self._settings.device == "cuda":
            if self._torch.cuda.is_available():
                self._torch.cuda.empty_cache()
        self._torch = None
