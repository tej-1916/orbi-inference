"""Security tests ensuring validation responses do not echo submitted input."""

import json

from fastapi.exceptions import RequestValidationError

from orbi_gateway.errors import validation_error_handler


async def test_validation_error_response_omits_sensitive_input() -> None:
    secret_prompt = "private prompt that must never be echoed"  # noqa: S105
    exc = RequestValidationError(
        [
            {
                "type": "string_too_long",
                "loc": ("body", "messages", 0, "content"),
                "msg": "String should have at most 100000 characters",
                "input": secret_prompt,
            }
        ]
    )
    response = await validation_error_handler(None, exc)  # type: ignore[arg-type]
    body = json.loads(response.body)
    assert secret_prompt not in response.body.decode()
    assert body["error"]["code"] == "request_validation_failed"
