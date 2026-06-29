"""Liveness endpoint; this route intentionally does not disclose internal dependency details."""

from fastapi import APIRouter

router = APIRouter(tags=["health"])


@router.get("/health")
async def health() -> dict[str, str]:
    """Return process liveness without exposing secrets or topology."""
    return {"status": "ok", "service": "orbi-gateway"}
