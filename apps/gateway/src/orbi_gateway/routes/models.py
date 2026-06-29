"""Public model-alias discovery endpoint."""

from fastapi import APIRouter
from sqlalchemy import select

from orbi_gateway.dependencies import ModelsAPIKeyDep, SessionDep
from orbi_gateway.models import ModelAlias

router = APIRouter(prefix="/v1", tags=["models"])


@router.get("/models")
async def list_models(_: ModelsAPIKeyDep, session: SessionDep) -> dict[str, object]:
    """List active aliases without exposing provider credentials or worker topology."""
    rows = (
        await session.execute(select(ModelAlias).where(ModelAlias.is_active.is_(True)))
    ).scalars()
    return {
        "object": "list",
        "data": [
            {
                "id": row.alias,
                "object": "model",
                "owned_by": "orbi",
                "orbi": {
                    "supports_streaming": row.supports_streaming,
                    "supports_tools": row.supports_tools,
                    "max_context_tokens": row.max_context_tokens,
                },
            }
            for row in rows
        ],
    }
