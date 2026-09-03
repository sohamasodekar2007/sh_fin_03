"""GET /v1/resources — the fleet, in the lightweight dashboard shape."""

from __future__ import annotations

from fastapi import APIRouter, Depends

from apps.api import mock_data
from apps.api.dependencies import get_current_user
from apps.api.pipeline import get_last_run
from packages.schemas.schemas import UserInDB
from packages.schemas.unified_resource import UnifiedResource

router = APIRouter(prefix="/v1", tags=["resources"])


@router.get("/resources")
async def list_resources(user: UserInDB = Depends(get_current_user)):
    run = get_last_run(user.tenant_id)
    if not run:
        return [r.model_dump() for r in mock_data.RESOURCES]

    resources = [UnifiedResource.model_validate(r) for r in run.get("observation", {}).get("resources", [])]
    return [r.to_dashboard_resource() for r in resources]


@router.get("/resources/unified")
async def list_unified_resources(user: UserInDB = Depends(get_current_user)):
    """FOCUS 1.0-shaped resources, straight off the last Monitor Agent run —
    what the multi-cloud cost catalog / a real FOCUS export consumer would read."""
    run = get_last_run(user.tenant_id)
    if not run:
        return []
    return run.get("observation", {}).get("resources", [])
