"""Controlled node failures that are safe to report to the gateway."""


class NodeError(Exception):
    """Base controlled failure with a stable, sanitized code."""

    def __init__(self, code: str, message: str, *, retryable: bool = True) -> None:
        super().__init__(message)
        self.code = code
        self.safe_message = message
        self.retryable = retryable


class AuthenticationError(NodeError):
    """The current worker credential is invalid or expired."""

    def __init__(self, message: str = "Worker authentication failed.") -> None:
        super().__init__("worker_authentication_failed", message, retryable=False)


class PermanentHTTPError(NodeError):
    """A permanent HTTP response that must not be retried."""

    def __init__(self, status_code: int) -> None:
        super().__init__(
            "permanent_gateway_response",
            f"Gateway rejected the request with HTTP {status_code}.",
            retryable=False,
        )
        self.status_code = status_code


class RetryExhaustedError(NodeError):
    """Transient gateway access failed within the bounded retry budget."""

    def __init__(self) -> None:
        super().__init__(
            "gateway_retry_exhausted",
            "Gateway request failed after bounded retries.",
        )


class UnknownRequestError(NodeError):
    """A result did not correspond to the worker's active assignment."""

    def __init__(self) -> None:
        super().__init__(
            "unknown_request_id",
            "Result request ID does not match the active assignment.",
            retryable=False,
        )
