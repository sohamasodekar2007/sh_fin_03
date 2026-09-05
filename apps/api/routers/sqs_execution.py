from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Query

from apps.api.config import get_settings
from apps.api.db import get_db
from apps.api.dependencies import CurrentUser
from services.messaging.sqs_execution_queue import ExecutionQueueDisabled, sqs_execution_configured
from services.messaging.sqs_execution_worker import process_execution_queue_batch, worker_status

router = APIRouter(prefix="/v1/sqs", tags=["sqs-execution"])


@router.get("/status", response_model=dict[str, Any])
async def sqs_status(current_user: CurrentUser) -> dict[str, Any]:
    settings = get_settings()
    return {
        **worker_status(),
        "enabled": sqs_execution_configured(settings),
        "queue_url_configured": bool(settings.sqs_execution_queue_url),
        "region": settings.aws_region,
        "tenant_id": current_user["tenant_id"],
    }


@router.post("/executions/process", response_model=dict[str, Any])
async def process_execution_queue(
    current_user: CurrentUser,
    limit: int = Query(default=5, ge=1, le=10),
) -> dict[str, Any]:
    try:
        return await process_execution_queue_batch(get_db(), limit=limit, tenant_id=current_user["tenant_id"])
    except ExecutionQueueDisabled as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
