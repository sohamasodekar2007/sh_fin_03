from typing import Any
from uuid import uuid4

from fastapi import APIRouter, Depends, Query

from apps.api.config import get_settings
from apps.api.db import get_db
from apps.api.dependencies import get_current_user
from apps.api.routers.agent_command import _live_aws_agent_command_doc, _mongo_available
from services.scheduler import run_pipeline_for_account

router = APIRouter(prefix="/v1/pipeline", tags=["pipeline"])


def _degraded_aws_pipeline_response(
    *,
    settings,
    run_id: str,
    account_id: str,
    region: str,
    error: str,
) -> dict[str, Any]:
    agent_command_doc = _live_aws_agent_command_doc(
        settings=settings,
        run_id=run_id,
        status="degraded",
        error=error,
    )
    summary = agent_command_doc.get("summary") or {}
    return {
        "run_id": run_id,
        "provider": "aws",
        "account_id": account_id,
        "region": region,
        "status": "degraded",
        "persistence_error": error,
        "monitor": {
            "status": "degraded",
            "resource_count": summary.get("resources", 0),
            "summary": {"total_resources": summary.get("resources", 0)},
        },
        "analyzer": {
            "status": "degraded",
            "findings_count": summary.get("findings", 0),
        },
        "decision": {
            "status": "degraded",
            "proposals_count": summary.get("proposals", 0),
            "proposals": agent_command_doc.get("proposals") or [],
            "llm_used": False,
        },
        "supervisor": {"status": "degraded", "summary": {"total": 0}},
        "agent_command_doc": agent_command_doc,
    }


@router.post("/run", response_model=dict[str, Any])
async def trigger_pipeline_run(
    provider: str | None = Query(default=None),
    account_id: str | None = Query(default=None),
    region: str | None = Query(default=None),
    current_user: dict = Depends(get_current_user),
) -> dict[str, Any]:
    """
    Manually trigger the same Monitor -> Analyzer -> Decision -> Supervisor
    chain the hourly scheduler runs (services/scheduler.py), for demos.
    Never auto-executes — proposals come out "pending_approval" or
    "blocked", never "approved".
    """
    settings = get_settings()
    tenant_id = current_user.get("tenant_id", "demo-tenant")
    provider = (provider or "aws").strip().lower()

    if provider == "aws":
        account_id = account_id or settings.aws_account_id
        region = region or settings.aws_region
    elif provider == "azure":
        account_id = account_id or settings.azure_subscription_id
        region = region or "global"
    elif provider == "vps":
        account_id = account_id or settings.vps_host
        region = region or "on-premises"
    else:
        region = region or ""

    run_id = str(uuid4())
    if provider == "aws" and not await _mongo_available(get_db()):
        return _degraded_aws_pipeline_response(
            settings=settings,
            run_id=run_id,
            account_id=account_id,
            region=region,
            error="MongoDB is unavailable; showing live AWS inventory without persisted pipeline artifacts.",
        )

    try:
        return await run_pipeline_for_account(tenant_id, provider, account_id, region, run_id=run_id)
    except Exception as exc:
        if provider != "aws":
            raise

        return _degraded_aws_pipeline_response(
            settings=settings,
            run_id=run_id,
            account_id=account_id,
            region=region,
            error=str(exc),
        )
