from __future__ import annotations

import asyncio
import json
import logging
from datetime import datetime, timezone
from typing import Any

from apps.api.config import get_settings
from apps.api.db import get_db
from packages.schemas.execution import LiveExecutionRecord
from services.executor.actions import assumed_write_session, execute_action
from services.messaging.sqs_execution_queue import (
    ExecutionQueueDisabled,
    delete_execution_message,
    receive_execution_messages,
    sqs_execution_configured,
)
from services.notifications.email import send_completion_email_sync
from services.verifier.health import verify_execution

logger = logging.getLogger(__name__)

_worker_task: asyncio.Task | None = None
_worker_state: dict[str, Any] = {
    "running": False,
    "started_at": None,
    "last_poll_at": None,
    "last_processed_at": None,
    "last_error": None,
    "last_error_at": None,
    "processed_total": 0,
}


def worker_status() -> dict[str, Any]:
    settings = get_settings()
    return {
        **_worker_state,
        "enabled": sqs_execution_configured(settings),
        "queue_url_configured": bool(settings.sqs_execution_queue_url),
        "poll_interval_seconds": 2,
    }


async def _dispatch_completion_email(db: Any, tenant_id: str, proposal_doc: dict[str, Any], record: LiveExecutionRecord) -> None:
    settings = get_settings()
    recipient = await db.users.find_one({"tenant_id": tenant_id}, {"_id": 0, "email": 1})
    to_email = (recipient or {}).get("email")
    if not to_email:
        logger.warning("sqs-worker: no user email on file for tenant %s; completion email not sent", tenant_id)
        return

    context = {
        "resource_arn": record.resource_arn,
        "action_type": record.action_type,
        "status": record.status,
        "predicted_savings_monthly": proposal_doc.get("expected_monthly_savings", "0"),
        "rollback_link": f"{settings.app_base_url}/dashboard?execution_id={record.execution_id}",
    }
    await asyncio.to_thread(send_completion_email_sync, to_email, context, settings)


async def _mark_queue_job(db: Any, message_id: str | None, fields: dict[str, Any]) -> None:
    if not message_id:
        return
    try:
        await db.execution_queue_jobs.update_one({"message_id": message_id}, {"$set": fields})
    except Exception:
        logger.exception("sqs-worker: failed to update queue job %s", message_id)


async def _process_one_message(db: Any, raw: dict[str, Any], tenant_id: str | None = None) -> dict[str, Any]:
    message_id = raw.get("MessageId")
    receipt_handle = raw.get("ReceiptHandle")
    received_at = datetime.now(timezone.utc)

    try:
        payload = json.loads(raw.get("Body") or "{}")
    except json.JSONDecodeError:
        logger.warning("sqs-worker: deleting malformed execution message %s", message_id)
        if receipt_handle:
            await delete_execution_message(receipt_handle)
        await _mark_queue_job(db, message_id, {"status": "deleted_malformed", "finished_at": received_at})
        return {"message_id": message_id, "status": "deleted_malformed"}

    proposal_id = payload.get("proposal_id")
    message_tenant_id = payload.get("tenant_id")
    if tenant_id is not None and message_tenant_id != tenant_id:
        return {"message_id": message_id, "status": "skipped_tenant_mismatch"}

    await _mark_queue_job(db, message_id, {"status": "processing", "started_at": received_at})
    proposal_doc = await db.proposals.find_one({"proposal_id": proposal_id, "tenant_id": message_tenant_id})
    if not proposal_doc:
        if receipt_handle:
            await delete_execution_message(receipt_handle)
        await _mark_queue_job(
            db,
            message_id,
            {"status": "deleted_missing_proposal", "proposal_id": proposal_id, "finished_at": datetime.now(timezone.utc)},
        )
        return {"message_id": message_id, "proposal_id": proposal_id, "status": "deleted_missing_proposal"}

    proposal_doc.pop("_id", None)
    if proposal_doc.get("status") not in {"approved", "queued_for_execution", "executing"}:
        if receipt_handle:
            await delete_execution_message(receipt_handle)
        await _mark_queue_job(
            db,
            message_id,
            {
                "status": "deleted_not_executable",
                "proposal_id": proposal_id,
                "proposal_status": proposal_doc.get("status"),
                "finished_at": datetime.now(timezone.utc),
            },
        )
        return {
            "message_id": message_id,
            "proposal_id": proposal_id,
            "status": "deleted_not_executable",
            "proposal_status": proposal_doc.get("status"),
        }

    await db.proposals.update_one(
        {"proposal_id": proposal_id, "tenant_id": message_tenant_id},
        {"$set": {"status": "executing", "execution_queue_message_id": message_id}},
    )

    executable_doc = dict(proposal_doc)
    executable_doc["status"] = "approved"
    record = await execute_action(db, executable_doc, run_id=payload.get("run_id") or proposal_id)

    verification: dict[str, Any] | None = None
    if record.status == "executed" and record.execution_mode == "live" and record.actual_aws_call_made:
        try:
            verification = await verify_execution(
                db,
                record,
                assumed_write_session(payload.get("run_id") or proposal_id),
            )
        except Exception:
            logger.exception("sqs-worker: verification failed for proposal %s", proposal_id)

    update_fields: dict[str, Any] = {
        "execution_id": record.execution_id,
        "execution_status": record.status,
        "execution_mode": record.execution_mode,
        "execution_reason_codes": record.reason_codes,
        "execution_before_state": record.before_state,
        "execution_after_state": record.after_state,
        "execution_rollback_descriptor": record.rollback_descriptor,
        "actual_aws_call_made": record.actual_aws_call_made,
    }
    if record.status in ("executed", "no_op"):
        update_fields["status"] = "executed"
    elif record.status == "refused":
        update_fields["status"] = "blocked"
    elif record.status in {"failed", "verification_failed"}:
        update_fields["status"] = "execution_failed"

    await db.proposals.update_one({"proposal_id": proposal_id, "tenant_id": message_tenant_id}, {"$set": update_fields})
    await _mark_queue_job(
        db,
        message_id,
        {
            "status": "processed",
            "execution_id": record.execution_id,
            "execution_status": record.status,
            "finished_at": datetime.now(timezone.utc),
        },
    )

    if receipt_handle:
        await delete_execution_message(receipt_handle)
    if record.status in ("executed", "no_op"):
        await _dispatch_completion_email(db, message_tenant_id, proposal_doc, record)

    _worker_state["processed_total"] = int(_worker_state.get("processed_total") or 0) + 1
    _worker_state["last_processed_at"] = datetime.now(timezone.utc).isoformat()
    return {
        "message_id": message_id,
        "proposal_id": proposal_id,
        "status": "processed",
        "execution_status": record.status,
        "verification": verification,
    }


async def process_execution_queue_batch(db: Any | None = None, *, limit: int | None = None, tenant_id: str | None = None) -> dict[str, Any]:
    db = db or get_db()
    try:
        messages = await receive_execution_messages(limit=limit)
    except ExecutionQueueDisabled:
        raise

    processed: list[dict[str, Any]] = []
    for raw in messages:
        try:
            processed.append(await _process_one_message(db, raw, tenant_id=tenant_id))
        except Exception as exc:
            message_id = raw.get("MessageId")
            logger.exception("sqs-worker: failed to process message %s; leaving it visible for retry", message_id)
            await _mark_queue_job(
                db,
                message_id,
                {
                    "status": "retry_pending",
                    "last_error": str(exc),
                    "last_failed_at": datetime.now(timezone.utc),
                },
            )
            processed.append({"message_id": message_id, "status": "retry_pending", "error": str(exc)})
    return {"processed": processed, "count": len(processed)}


async def _worker_loop() -> None:
    settings = get_settings()
    _worker_state.update(
        {
            "running": True,
            "started_at": datetime.now(timezone.utc).isoformat(),
            "last_error": None,
        }
    )
    logger.info("sqs-worker: started")
    try:
        while True:
            _worker_state["last_poll_at"] = datetime.now(timezone.utc).isoformat()
            try:
                await process_execution_queue_batch(limit=settings.sqs_max_messages)
                _worker_state["last_error"] = None
            except ExecutionQueueDisabled:
                logger.info("sqs-worker: disabled; stopping")
                return
            except Exception as exc:
                _worker_state["last_error"] = str(exc)
                _worker_state["last_error_at"] = datetime.now(timezone.utc).isoformat()
                logger.exception("sqs-worker: poll failed")
                await asyncio.sleep(15)
                continue
            await asyncio.sleep(2)
    except asyncio.CancelledError:
        logger.info("sqs-worker: cancelled")
        raise
    finally:
        _worker_state["running"] = False


def start_execution_queue_worker() -> asyncio.Task | None:
    global _worker_task
    settings = get_settings()
    if not sqs_execution_configured(settings):
        logger.info("sqs-worker: SQS execution disabled or queue URL missing")
        return None
    if _worker_task is not None and not _worker_task.done():
        return _worker_task
    _worker_task = asyncio.create_task(_worker_loop(), name="cloudcare-sqs-execution-worker")
    return _worker_task


async def stop_execution_queue_worker() -> None:
    global _worker_task
    if _worker_task is None:
        return
    _worker_task.cancel()
    try:
        await _worker_task
    except asyncio.CancelledError:
        pass
    _worker_task = None
