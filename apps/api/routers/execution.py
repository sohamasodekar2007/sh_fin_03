"""
Executor Router (Phase 6) — POST /v1/execute/{proposal_id} is called by the
approval flow (apps/api/routers/supervisor.py), not directly by a user; the
other two routes are dashboard-facing (JWT).
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, BackgroundTasks, HTTPException, Query

from apps.api.config import get_settings
from apps.api.db import get_db
from apps.api.dependencies import CurrentUser
from packages.schemas.execution import LiveExecutionRecord
from services.executor.actions import ExecutionRefused, assumed_write_session, execute_action, execute_rollback
from services.notifications.email import send_completion_email_sync
from services.verifier.health import verify_execution

router = APIRouter(prefix="/v1", tags=["executor"])


def _execution_update_fields(record: LiveExecutionRecord) -> dict[str, Any]:
    return {
        "execution_id": record.execution_id,
        "execution_status": record.status,
        "execution_mode": record.execution_mode,
        "execution_reason_codes": record.reason_codes,
        "execution_before_state": record.before_state,
        "execution_after_state": record.after_state,
        "execution_rollback_descriptor": record.rollback_descriptor,
        "actual_aws_call_made": record.actual_aws_call_made,
    }


async def _record_from_doc(doc: dict[str, Any]) -> LiveExecutionRecord:
    doc = dict(doc)
    doc.pop("_id", None)
    return LiveExecutionRecord(**doc)


async def _dispatch_completion_email(
    db, background_tasks: BackgroundTasks | None, tenant_id: str, proposal_doc: dict[str, Any], record: LiveExecutionRecord
) -> None:
    settings = get_settings()
    recipient = await db.users.find_one({"tenant_id": tenant_id}, {"_id": 0, "email": 1})
    to_email = (recipient or {}).get("email")
    if not to_email:
        return

    context = {
        "resource_arn": record.resource_arn,
        "action_type": record.action_type,
        "status": record.status,
        "predicted_savings_monthly": proposal_doc.get("expected_monthly_savings", "0"),
        "rollback_link": f"{settings.app_base_url}/dashboard?execution_id={record.execution_id}",
    }
    if background_tasks is not None:
        background_tasks.add_task(send_completion_email_sync, to_email, context, settings)
    else:
        send_completion_email_sync(to_email, context, settings)


@router.post("/execute/{proposal_id}", response_model=dict[str, Any])
async def execute_proposal(
    proposal_id: str,
    current_user: CurrentUser,
    background_tasks: BackgroundTasks = None,
) -> dict[str, Any]:
    db = get_db()
    tenant_id = current_user["tenant_id"]

    proposal_doc = await db.proposals.find_one({"proposal_id": proposal_id, "tenant_id": tenant_id})
    if not proposal_doc:
        raise HTTPException(status_code=404, detail="Proposal not found")
    proposal_doc.pop("_id", None)

    record = await execute_action(db, proposal_doc, run_id=proposal_id)

    verification: dict[str, Any] | None = None
    if record.status == "executed" and record.execution_mode == "live" and record.actual_aws_call_made:
        try:
            settings = get_settings()
            session = assumed_write_session(proposal_id)
            verification = await verify_execution(db, record, session)
        except ExecutionRefused:
            verification = None

    update_fields = _execution_update_fields(record)
    if record.status in ("executed", "no_op"):
        update_fields["status"] = "executed"

    await db.proposals.update_one(
        {"proposal_id": proposal_id, "tenant_id": tenant_id},
        {"$set": update_fields},
    )

    if record.status in ("executed", "no_op"):
        await _dispatch_completion_email(db, background_tasks, tenant_id, proposal_doc, record)

    return {"execution": record.model_dump(mode="json"), "verification": verification}


@router.get("/executions", response_model=list[dict[str, Any]])
async def list_executions(current_user: CurrentUser, run_id: str | None = Query(default=None)) -> list[dict[str, Any]]:
    db = get_db()
    tenant_id = current_user["tenant_id"]

    query: dict[str, Any] = {"tenant_id": tenant_id}
    if run_id:
        query["run_id"] = run_id

    return await db.execution_audit.find(query, {"_id": 0}).to_list(length=None)


@router.post("/executions/{execution_id}/rollback", response_model=dict[str, Any])
async def rollback_execution(execution_id: str, current_user: CurrentUser) -> dict[str, Any]:
    db = get_db()
    tenant_id = current_user["tenant_id"]

    doc = await db.execution_audit.find_one({"execution_id": execution_id, "tenant_id": tenant_id})
    if not doc:
        raise HTTPException(status_code=404, detail="Execution record not found")

    record = await _record_from_doc(doc)
    if not record.rollback_descriptor:
        raise HTTPException(status_code=400, detail="This execution has no rollback descriptor")

    result = await execute_rollback(db, record)
    if result is None:
        raise HTTPException(
            status_code=400,
            detail=f"Rollback for {record.action_type} requires manual action — see rollback_descriptor: {record.rollback_descriptor}",
        )
    return {"rollback": result.model_dump(mode="json")}
