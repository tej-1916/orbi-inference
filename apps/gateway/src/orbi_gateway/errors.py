"""Safe application errors that never expose internal tracebacks or submitted prompt content."""

from typing import Any

import structlog
from fastapi import Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

logger = structlog.get_logger(__name__)


class OrbiError(Exception):
    """Base exception carrying a stable public error code and HTTP status."""

    def __init__(self, code: str, message: str, status_code: int) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.status_code = status_code


async def orbi_error_handler(_: Request, exc: OrbiError) -> JSONResponse:
    """Render an ORBI error without implementation details."""
    return JSONResponse(
        status_code=exc.status_code,
        content={"error": {"code": exc.code, "message": exc.message}},
    )


async def validation_error_handler(_: Request, exc: RequestValidationError) -> JSONResponse:
    """Return validation locations and messages while omitting raw input values."""
    details: list[dict[str, Any]] = []
    for error in exc.errors():
        details.append(
            {
                "location": [str(part) for part in error.get("loc", ())],
                "message": str(error.get("msg", "Invalid request value.")),
                "type": str(error.get("type", "validation_error")),
            }
        )
    return JSONResponse(
        status_code=422,
        content={
            "error": {
                "code": "request_validation_failed",
                "message": "Request validation failed.",
                "details": details,
            }
        },
    )


async def unexpected_error_handler(_: Request, exc: Exception) -> JSONResponse:
    """Fail closed and log only the exception class, never its possibly sensitive message."""
    await logger.aerror("unhandled_exception", exception_type=type(exc).__name__)
    return JSONResponse(
        status_code=500,
        content={
            "error": {
                "code": "internal_error",
                "message": "The request could not be completed.",
            }
        },
    )
