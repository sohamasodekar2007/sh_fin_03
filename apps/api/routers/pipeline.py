from typing import Any

from fastapi import APIRouter, Depends, Query

from apps.api.config import get_settings
from apps.api.dependencies import get_current_user
from services.scheduler import run_pipeline_for_account

router = APIRouter(prefix="/v1/pipeline", tags=["pipeline"])


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

    return await run_pipeline_for_account(tenant_id, provider, account_id, region)
