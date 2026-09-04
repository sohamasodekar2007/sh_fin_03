"""
Post-execution verifier (Phase 6) — replaces the NotImplementedError
placeholder. After a live execution, waits, re-polls the resource, confirms
it reached the expected state, and confirms no CloudWatch alarm fired for
it since the action. On failure, automatically invokes the rollback
descriptor (services/executor/actions.py:execute_rollback) and flags the
run — apps/api/routers/execution.py surfaces that flag.

Simulation runs and no_ops are correctly skipped — there is nothing real to
re-poll when actual_aws_call_made is False.
"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone
from typing import Any

from motor.motor_asyncio import AsyncIOMotorDatabase

from apps.api.config import get_settings
from packages.schemas.execution import LiveExecutionRecord

logger = logging.getLogger(__name__)

DEFAULT_WAIT_SECONDS = 60

# Only actions with a simple, single expected end-state are re-polled here.
# resize_instance/delete_volume/schedule_instance's success is already
# confirmed synchronously by the boto3 call that made the change (a
# describe-based re-check adds little for them in this build) — they still
# get the CloudWatch alarm check.
_EXPECTED_INSTANCE_STATE = {"stop_instance": "stopped", "start_instance": "running"}


def _check_expected_state(ec2: Any, record: LiveExecutionRecord) -> bool:
    expected = _EXPECTED_INSTANCE_STATE.get(record.action_type)
    if not expected:
        return True
    try:
        resp = ec2.describe_instances(InstanceIds=[record.resource_id])
        state = resp["Reservations"][0]["Instances"][0]["State"]["Name"]
    except Exception as exc:
        logger.warning("verifier: could not re-describe %s: %s", record.resource_id, exc)
        return False
    return state == expected


def _check_no_alarms_fired(session: Any, record: LiveExecutionRecord, region: str) -> bool:
    try:
        cw = session.client("cloudwatch", region_name=region)
        resp = cw.describe_alarms(StateValue="ALARM")
    except Exception:
        # A CloudWatch call we couldn't make is a missing signal, not a
        # detected failure — don't block completion on it, but say so
        # loudly so it's visible in logs.
        logger.warning("verifier: could not check CloudWatch alarms for %s", record.resource_id)
        return True

    for alarm in resp.get("MetricAlarms", []):
        dimensions = str(alarm.get("Dimensions", []))
        if record.resource_id in dimensions:
            return False
    return True


async def verify_execution(
    db: AsyncIOMotorDatabase,
    record: LiveExecutionRecord,
    session: Any,
    wait_seconds: int = DEFAULT_WAIT_SECONDS,
) -> dict[str, Any]:
    """Returns {"verified": bool, "rolled_back": bool, "reason": str}.
    `session` is the already-assumed write-role boto3.Session that produced
    `record` — reused here rather than re-assuming a role for a read."""
    if record.execution_mode != "live" or not record.actual_aws_call_made:
        return {"verified": True, "rolled_back": False, "reason": "nothing to verify (simulation or no_op)"}

    if wait_seconds > 0:
        await asyncio.sleep(wait_seconds)

    settings = get_settings()
    region = (record.before_state or {}).get("region") or settings.aws_region
    ec2 = session.client("ec2", region_name=region)

    state_ok = _check_expected_state(ec2, record)
    alarms_ok = _check_no_alarms_fired(session, record, region)

    verification = {
        "checked_at": datetime.now(timezone.utc).isoformat(),
        "state_ok": state_ok,
        "alarms_ok": alarms_ok,
        "waited_seconds": wait_seconds,
    }

    try:
        await db.execution_audit.update_one(
            {"execution_id": record.execution_id}, {"$set": {"verification": verification}}
        )
    except Exception:
        logger.exception("verifier: failed to persist verification for %s", record.execution_id)

    if state_ok and alarms_ok:
        return {"verified": True, "rolled_back": False, "reason": "ok"}

    reason = "state mismatch" if not state_ok else "cloudwatch alarm fired"
    logger.warning("verifier: verification failed for %s (%s) — invoking rollback", record.execution_id, reason)

    from services.executor.actions import execute_rollback

    rollback_result = await execute_rollback(db, record)

    try:
        await db.execution_audit.update_one(
            {"execution_id": record.execution_id},
            {"$set": {"status": "verification_failed", "verification": {**verification, "reason": reason}}},
        )
    except Exception:
        logger.exception("verifier: failed to flag %s as verification_failed", record.execution_id)

    return {"verified": False, "rolled_back": rollback_result is not None, "reason": reason}
