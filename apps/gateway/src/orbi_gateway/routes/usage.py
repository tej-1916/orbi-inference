"""Project usage endpoint backed by committed PostgreSQL accounting records."""

from fastapi import APIRouter
from sqlalchemy import select

from orbi_gateway.dependencies import SessionDep, UsageAPIKeyDep
from orbi_gateway.models import Project

router = APIRouter(prefix="/v1", tags=["usage"])


@router.get("/usage")
async def get_usage(api_key: UsageAPIKeyDep, session: SessionDep) -> dict[str, object]:
    """Return current project token budgets and this key's durable completion totals."""
    project = (
        await session.execute(select(Project).where(Project.id == api_key.project_id))
    ).scalar_one()
    return {
        "object": "orbi.usage",
        "project_id": str(project.id),
        "daily": {
            "date": project.daily_usage_date.isoformat(),
            "tokens_used_or_reserved": project.daily_tokens_used,
            "token_limit": project.daily_token_limit,
        },
        "monthly": {
            "month": project.monthly_usage_month.isoformat(),
            "tokens_used_or_reserved": project.monthly_tokens_used,
            "token_limit": project.monthly_token_limit,
        },
        "api_key": {
            "display_prefix": api_key.display_prefix,
            "completed_requests": api_key.total_requests,
            "completed_tokens": api_key.total_tokens,
            "daily_requests_used": api_key.daily_requests_used,
            "daily_request_limit": api_key.daily_req_limit,
        },
    }
