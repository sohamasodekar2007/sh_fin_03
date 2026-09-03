"""
GET-only "latest run" readouts for the dashboard's Monitor/Analyzer agent
control panels — POST /v1/runs (accounts_runs.py) is the only thing that
actually triggers the pipeline; these just read apps/api/pipeline's cache
so the panels have something to render on mount without re-running it.
"""

from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Depends

from apps.api.dependencies import get_current_user
from apps.api.pipeline import get_last_run
from packages.schemas.schemas import UserInDB

router = APIRouter(prefix="/v1", tags=["observation"])


@router.get("/observation/latest")
async def observation_latest(user: UserInDB = Depends(get_current_user)):
    run = get_last_run(user.tenant_id)
    if not run:
        return None
    observation = run.get("observation", {})
    resources = observation.get("resources", [])
    idle = sum(1 for f in run.get("findings", []) if f["rule_id"] == "ec2.idle.v1")
    oversized = sum(1 for f in run.get("findings", []) if f["rule_id"] == "ec2.overprovisioned.v1")
    unattached = sum(1 for f in run.get("findings", []) if f["rule_id"] == "ebs.unattached.v1")
    return {
        "run_id": run.get("run_id"),
        "summary": {
            "total_resources": len(resources),
            "metrics_collected": len(resources),
            "idle_instances_detected": idle,
            "oversized_instances_detected": oversized,
            "unattached_ebs_volumes_detected": unattached,
        },
        "resources": resources,
        "providers": observation.get("providers", {}),
    }


@router.get("/findings/latest")
async def findings_latest(user: UserInDB = Depends(get_current_user)):
    run = get_last_run(user.tenant_id)
    if not run:
        return None
    findings = run.get("findings", [])
    return {"findings_count": len(findings), "findings": findings, "timestamp": datetime.now(timezone.utc).isoformat()}
