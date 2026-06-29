"""Security middleware tests for body limits and response headers."""

from fastapi import FastAPI, Request
from fastapi.testclient import TestClient

from orbi_gateway.middleware import SecurityMiddleware


def make_app(max_body_bytes: int = 1024) -> FastAPI:
    """Create a tiny application isolated from ORBI database dependencies."""
    app = FastAPI()
    app.add_middleware(SecurityMiddleware, max_body_bytes=max_body_bytes)

    @app.post("/echo-size")
    async def echo_size(request: Request) -> dict[str, int]:
        body = await request.body()
        return {"size": len(body)}

    return app


def test_security_middleware_rejects_oversized_body_without_echoing_it() -> None:
    body = "s" * 2048
    with TestClient(make_app()) as client:
        response = client.post("/echo-size", content=body)
    assert response.status_code == 413
    assert body not in response.text
    assert response.headers["cache-control"] == "no-store"
    assert response.headers["x-content-type-options"] == "nosniff"


def test_security_middleware_adds_request_id_and_no_store_headers() -> None:
    with TestClient(make_app()) as client:
        response = client.post("/echo-size", content="safe")
    assert response.status_code == 200
    assert response.headers["cache-control"] == "no-store"
    assert response.headers["x-content-type-options"] == "nosniff"
    assert response.headers["x-orbi-request-id"]
