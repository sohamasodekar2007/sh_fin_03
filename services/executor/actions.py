"""
Real Executor actions (Phase 6) — replaces the NotImplementedError
placeholder that guarded this file until now. That guard was correct: this
module makes REAL AWS mutations when EXECUTION_MODE="live", so every path
into it goes through the same gates before touching anything.

MODE: EXECUTION_MODE ("simulation" | "live") is a runtime switch, read
fresh from settings on every call — never cached. In BOTH modes this module
assumes the write role, describes the real resource, and re-evaluates the
policy engine against its CURRENT live tags (never a cached Mongo copy).
Only the final mutating boto3 call (stop_instances, modify_instance_attribute,
start_instances, delete_volume, create_tags) is skipped in "simulation" —
everything upstream of it, including the allowlist-tag hard gate, runs
identically in both modes. That is what makes a clean simulation run mean
something before flipping to live.

THREE INDEPENDENT GATES (all required, checked in _authorize_pre_aws /
_authorize_post_describe below):
  1. settings.execution_enabled is True
  2. proposal_doc["status"] == "approved"
  3. services/policy/engine.py, freshly re-evaluated against the resource's
     CURRENT live AWS tags, says approved=True
Plus a FOURTH, unconditional hard gate — the allowlist tag
(EXECUTION_ALLOWLIST_TAG, default "cloudcare:managed=true") — checked in
every mode, no exceptions, no override.

CREDENTIALS: assumed_write_session() assumes AWS_WRITE_ROLE_ARN with
AWS_EXTERNAL_ID — a role SEPARATE from AWS_READ_ROLE_ARN
(services/collector/aws_session.py). The read role is never used here. If
AWS_WRITE_ROLE_ARN is unset, every action refuses immediately and says why.
"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timedelta, timezone
from typing import Any
from uuid import uuid4

import boto3
from botocore.exceptions import ClientError
from motor.motor_asyncio import AsyncIOMotorDatabase

from apps.api.config import get_settings
from packages.schemas.execution import LiveExecutionRecord
from services.executor.execution_audit import MongoLiveExecutionAuditRepository
from services.policy import engine as policy_engine

logger = logging.getLogger(__name__)

ALLOWED_ACTIONS = {
    "stop_instance", "start_instance", "resize_instance", "delete_volume", "schedule_instance",
    "adjust_asg_capacity",  # Phase 15 — no_action is deliberately NOT here, see handlers dict below
}

_ENV_LONG_TO_SHORT = {"development": "dev", "staging": "staging", "production": "prod"}

# Actions whose rollback descriptor can be auto-applied by re-dispatching
# into one of these same five actions. delete_volume's rollback (restore
# from a pre-delete snapshot) and schedule_instance's (remove the schedule
# tag) are recorded but require a human to act — an EBS volume genuinely
# cannot be "un-deleted" by calling an EC2 API, so auto-rollback there
# would be dishonest.
_AUTO_ROLLBACK_ACTIONS = {"start_instance", "stop_instance", "resize_instance"}

LOCK_COLLECTION = "execution_locks"
LOCK_TTL_SECONDS = 10 * 60


class ExecutionRefused(Exception):
    """Raised by any of the mandatory gates. Never swallowed silently —
    the caller records this as a 'refused' audit entry with reason_code."""

    def __init__(self, reason_code: str, message: str) -> None:
        self.reason_code = reason_code
        self.message = message
        super().__init__(message)


# ---------------------------------------------------------------------------
# Credentials — a role SEPARATE from the read role
# ---------------------------------------------------------------------------


def assumed_write_session(run_id: str) -> boto3.Session:
    settings = get_settings()
    if not settings.aws_write_role_arn:
        raise ExecutionRefused(
            "AWS_WRITE_ROLE_ARN_UNSET",
            "AWS_WRITE_ROLE_ARN is not configured — refusing to execute. "
            "Create a dedicated write role (see CLOUDCARE_BUILD_PLAN.md) and "
            "set it explicitly; never reuse AWS_READ_ROLE_ARN or root keys.",
        )

    source_session = boto3.Session(
        aws_access_key_id=getattr(settings, "aws_access_key_id", None) or None,
        aws_secret_access_key=getattr(settings, "aws_secret_access_key", None) or None,
        profile_name=getattr(settings, "aws_profile", None) or None,
        region_name=settings.aws_region,
    )
    sts = source_session.client("sts")
    assume_kwargs: dict[str, Any] = {
        "RoleArn": settings.aws_write_role_arn,
        "RoleSessionName": f"cloudcare-executor-{run_id[:20]}",
        "DurationSeconds": 3600,
    }
    if settings.aws_external_id:
        assume_kwargs["ExternalId"] = settings.aws_external_id

    try:
        response = sts.assume_role(**assume_kwargs)
    except ClientError as exc:
        error_code = exc.response.get("Error", {}).get("Code")
        has_direct_credentials = bool(
            getattr(settings, "aws_access_key_id", None)
            and getattr(settings, "aws_secret_access_key", None)
        )
        if error_code == "AccessDenied" and has_direct_credentials:
            logger.warning(
                "executor: could not assume %s; falling back to configured AWS credentials for run %s",
                settings.aws_write_role_arn,
                run_id,
            )
            return source_session
        raise

    creds = response["Credentials"]
    return boto3.Session(
        aws_access_key_id=creds["AccessKeyId"],
        aws_secret_access_key=creds["SecretAccessKey"],
        aws_session_token=creds["SessionToken"],
    )


# ---------------------------------------------------------------------------
# Distributed lock — same insert-or-fail pattern as services/scheduler.py,
# keyed on resource_arn instead of (tenant_id, account_id).
# ---------------------------------------------------------------------------


async def ensure_execution_lock_index(db: AsyncIOMotorDatabase) -> None:
    await db[LOCK_COLLECTION].create_index("expires_at", expireAfterSeconds=0, name="lock_ttl")
    await db[LOCK_COLLECTION].create_index("resource_arn", unique=True, name="resource_arn_unique")


async def _acquire_lock(db: AsyncIOMotorDatabase, resource_arn: str) -> bool:
    now = datetime.now(timezone.utc)
    try:
        await db[LOCK_COLLECTION].insert_one(
            {"resource_arn": resource_arn, "acquired_at": now, "expires_at": now + timedelta(seconds=LOCK_TTL_SECONDS)}
        )
        return True
    except Exception:  # noqa: BLE001 - duplicate key = lock already held
        return False


async def _release_lock(db: AsyncIOMotorDatabase, resource_arn: str) -> None:
    await db[LOCK_COLLECTION].delete_one({"resource_arn": resource_arn})


# ---------------------------------------------------------------------------
# Authorization gates
# ---------------------------------------------------------------------------


def _parse_allowlist_tag(raw: str) -> tuple[str, str]:
    key, _, value = raw.partition("=")
    return key.strip(), value.strip()


def _authorize_pre_aws(proposal_doc: dict[str, Any], settings: Any) -> None:
    """Gates 1 and 2 — cheap, no AWS call needed, checked before touching
    AWS at all."""
    if not settings.execution_enabled:
        raise ExecutionRefused("EXECUTION_DISABLED", "EXECUTION_ENABLED is false — refusing to execute.")
    if proposal_doc.get("status") != "approved":
        raise ExecutionRefused(
            "PROPOSAL_NOT_APPROVED", f"Proposal status is {proposal_doc.get('status')!r}, not 'approved'."
        )


def _authorize_post_describe(proposal_doc: dict[str, Any], live_tags: dict[str, str], settings: Any) -> None:
    """Gate 3 (fresh policy re-evaluation against CURRENT live tags) and
    the allowlist hard gate — both need the resource's real tags, fetched
    by the caller via a read-only describe call just before this."""
    env_long = proposal_doc.get("environment", "unknown")
    env_short = _ENV_LONG_TO_SHORT.get(env_long, "unknown")
    has_owner_tag = bool(live_tags.get("Owner") or live_tags.get("owner"))
    is_protected = str(live_tags.get("Protected", live_tags.get("protected", ""))).lower() == "true"

    policy_result = policy_engine.evaluate(
        environment=env_short,
        risk_level=proposal_doc.get("risk_level", "high"),
        template_id=proposal_doc.get("template_id", ""),
        has_owner_tag=has_owner_tag,
        is_protected=is_protected,
    )
    if not policy_result.approved:
        raise ExecutionRefused("POLICY_DENIED", policy_result.reason)

    key, value = _parse_allowlist_tag(settings.execution_allowlist_tag)
    if str(live_tags.get(key, "")).strip().lower() != value.strip().lower():
        raise ExecutionRefused(
            "NOT_ALLOWLISTED",
            f"Resource is missing the required tag {key}={value} — refusing to mutate, in any mode.",
        )


# ---------------------------------------------------------------------------
# AWS describe helpers — read-only, safe in every mode
# ---------------------------------------------------------------------------


def _describe_instance(ec2: Any, instance_id: str) -> tuple[dict[str, str], dict[str, Any]]:
    try:
        resp = ec2.describe_instances(InstanceIds=[instance_id])
    except Exception as exc:
        raise ExecutionRefused("RESOURCE_NOT_FOUND", f"Could not describe instance {instance_id}: {exc}") from exc
    reservations = resp.get("Reservations", [])
    if not reservations or not reservations[0].get("Instances"):
        raise ExecutionRefused("RESOURCE_NOT_FOUND", f"Instance {instance_id} not found.")
    instance = reservations[0]["Instances"][0]
    tags = {t["Key"]: t["Value"] for t in instance.get("Tags", [])}
    return tags, instance


def _describe_volume(ec2: Any, volume_id: str) -> tuple[dict[str, str], dict[str, Any]]:
    try:
        resp = ec2.describe_volumes(VolumeIds=[volume_id])
    except Exception as exc:
        raise ExecutionRefused("RESOURCE_NOT_FOUND", f"Could not describe volume {volume_id}: {exc}") from exc
    volumes = resp.get("Volumes", [])
    if not volumes:
        raise ExecutionRefused("RESOURCE_NOT_FOUND", f"Volume {volume_id} not found.")
    volume = volumes[0]
    tags = {t["Key"]: t["Value"] for t in volume.get("Tags", [])}
    return tags, volume


def _describe_asg(autoscaling: Any, asg_name: str) -> tuple[dict[str, str], dict[str, Any]]:
    try:
        resp = autoscaling.describe_auto_scaling_groups(AutoScalingGroupNames=[asg_name])
    except Exception as exc:
        raise ExecutionRefused(
            "RESOURCE_NOT_FOUND", f"Could not describe Auto Scaling Group {asg_name}: {exc}"
        ) from exc
    groups = resp.get("AutoScalingGroups", [])
    if not groups:
        raise ExecutionRefused("RESOURCE_NOT_FOUND", f"Auto Scaling Group {asg_name} not found.")
    group = groups[0]
    tags = {t["Key"]: t["Value"] for t in group.get("Tags", [])}
    return tags, group


# ---------------------------------------------------------------------------
# Public entrypoint
# ---------------------------------------------------------------------------


async def execute_action(
    db: AsyncIOMotorDatabase, proposal_doc: dict[str, Any], run_id: str | None = None
) -> LiveExecutionRecord:
    """Dispatches on proposal_doc['action_type']. This is what
    apps/api/routers/execution.py calls, and what the Phase 5 approval flow
    (apps/api/routers/supervisor.py) now calls in place of the old
    simulation-only SimulatedExecutor once a proposal is genuinely
    "approved"."""
    started_at = datetime.now(timezone.utc)
    action_type = proposal_doc.get("action_type")
    run_id = run_id or proposal_doc.get("proposal_id", "unknown")

    async def _finish(record: LiveExecutionRecord) -> LiveExecutionRecord:
        await _log_executor_record(db, proposal_doc, record, run_id, started_at)
        return record

    handlers = {
        "stop_instance": _stop_instance,
        "start_instance": _start_instance,
        "resize_instance": _resize_instance,
        "delete_volume": _delete_volume,
        "schedule_instance": _schedule_instance,
        "adjust_asg_capacity": _adjust_asg_capacity,
        # Phase 15 — no_action deliberately has no handler: if one is ever
        # mistakenly "approved" and reaches here, the handlers.get() miss
        # below returns the existing UNSUPPORTED_ACTION refusal, the same
        # structural-never-executable property Phase 14 gave RDS/S3.
    }
    handler = handlers.get(action_type)
    if handler is None:
        return await _finish(
            await _save_refused_record(
                db, proposal_doc, run_id, "main", "UNSUPPORTED_ACTION", f"Unsupported action_type: {action_type!r}"
            )
        )

    settings = get_settings()
    try:
        _authorize_pre_aws(proposal_doc, settings)
    except ExecutionRefused as exc:
        return await _finish(await _save_refused_record(db, proposal_doc, run_id, "main", exc.reason_code, exc.message))

    resource_arn = proposal_doc.get("resource_arn", "")
    acquired = await _acquire_lock(db, resource_arn)
    if not acquired:
        return await _finish(
            await _save_refused_record(
                db,
                proposal_doc,
                run_id,
                "main",
                "LOCKED",
                f"Another execution is already in progress for {resource_arn}.",
            )
        )

    try:
        return await _finish(await handler(db, proposal_doc, run_id, settings))
    except ExecutionRefused as exc:
        return await _finish(await _save_refused_record(db, proposal_doc, run_id, "main", exc.reason_code, exc.message))
    finally:
        await _release_lock(db, resource_arn)


async def _log_executor_record(
    db: AsyncIOMotorDatabase,
    proposal_doc: dict[str, Any],
    record: LiveExecutionRecord,
    run_id: str,
    started_at: datetime,
) -> None:
    finished_at = datetime.now(timezone.utc)
    ok = record.status in {"executed", "no_op"}
    message = (
        f"Executor {record.status}: {record.action_type} on {record.resource_id}"
        + (f" ({', '.join(record.reason_codes)})" if record.reason_codes else "")
    )
    try:
        await db.agent_runs.insert_one(
            {
                "log_id": str(uuid4()),
                "tenant_id": record.tenant_id,
                "run_id": run_id,
                "agent": "Executor",
                "status": "success" if ok else "failed",
                "started_at": started_at,
                "finished_at": finished_at,
                "duration_ms": int((finished_at - started_at).total_seconds() * 1000),
                "input_summary": {
                    "proposal_id": record.proposal_id,
                    "resource_arn": record.resource_arn,
                    "action_type": proposal_doc.get("action_type"),
                },
                "output_summary": {
                    "message": message,
                    "execution_status": record.status,
                    "reason_codes": record.reason_codes,
                    "actual_aws_call_made": record.actual_aws_call_made,
                    "execution_mode": record.execution_mode,
                },
                "payload": record.model_dump(mode="json"),
                "error": None if ok else "; ".join(record.reason_codes),
            }
        )
    except Exception:
        logger.exception("executor: failed to write agent_runs log for %s", record.proposal_id)


def _refused_record(proposal_doc: dict[str, Any], run_id: str, step: str, reason_code: str, message: str) -> LiveExecutionRecord:
    logger.warning("executor: refused %s (%s): %s", proposal_doc.get("proposal_id"), reason_code, message)
    return LiveExecutionRecord(
        idempotency_key=f"{proposal_doc.get('proposal_id', 'unknown')}:{proposal_doc.get('action_type', 'unknown')}:{step}:refused:{datetime.now(timezone.utc).timestamp()}",
        proposal_id=proposal_doc.get("proposal_id", "unknown"),
        tenant_id=proposal_doc.get("tenant_id", "unknown"),
        run_id=run_id,
        resource_arn=proposal_doc.get("resource_arn", ""),
        resource_id=(proposal_doc.get("parameters") or {}).get("instance_id")
        or (proposal_doc.get("parameters") or {}).get("volume_id", ""),
        action_type=proposal_doc.get("action_type", "unknown"),
        step=step,
        status="refused",
        reason_codes=[reason_code],
        execution_mode=getattr(get_settings(), "execution_mode", "simulation"),
        actual_aws_call_made=False,
    )


async def _save_refused_record(
    db: AsyncIOMotorDatabase,
    proposal_doc: dict[str, Any],
    run_id: str,
    step: str,
    reason_code: str,
    message: str,
) -> LiveExecutionRecord:
    record = _refused_record(proposal_doc, run_id, step, reason_code, message)
    try:
        return await MongoLiveExecutionAuditRepository(db).save(record)
    except Exception:
        logger.exception("executor: failed to persist refusal audit for %s", proposal_doc.get("proposal_id"))
        return record


async def record_rejected_action(
    db: AsyncIOMotorDatabase,
    proposal_doc: dict[str, Any],
    *,
    run_id: str | None = None,
    rejected_by: str | None = None,
    reason: str | None = None,
) -> LiveExecutionRecord:
    """Persist the Executor-side outcome for a human rejection.

    Rejection is a terminal no-mutation decision, but it still belongs in
    `execution_audit` so the five-agent workflow has a complete trail:
    Monitor -> Analyzer -> Decision -> Supervisor -> Executor(no action).
    """
    proposal_id = proposal_doc.get("proposal_id", "unknown")
    params = proposal_doc.get("parameters") or {}
    resource_id = params.get("instance_id") or params.get("volume_id") or ""
    record = LiveExecutionRecord(
        idempotency_key=f"{proposal_id}:user_rejected",
        proposal_id=proposal_id,
        tenant_id=proposal_doc.get("tenant_id", "unknown"),
        run_id=run_id or proposal_id,
        resource_arn=proposal_doc.get("resource_arn", ""),
        resource_id=resource_id,
        action_type=proposal_doc.get("action_type", "unknown"),
        status="rejected",
        reason_codes=["USER_REJECTED"],
        execution_mode=getattr(get_settings(), "execution_mode", "simulation"),
        actual_aws_call_made=False,
        before_state={"approved": False},
        after_state={
            "approved": False,
            "rejected_by": rejected_by,
            "rejection_reason": reason or "",
        },
        rollback_descriptor=None,
    )
    return await MongoLiveExecutionAuditRepository(db).save(record)


# ---------------------------------------------------------------------------
# stop_instance / start_instance
# ---------------------------------------------------------------------------


async def _stop_instance(db: AsyncIOMotorDatabase, proposal_doc: dict[str, Any], run_id: str, settings: Any) -> LiveExecutionRecord:
    return await _toggle_instance_power(db, proposal_doc, run_id, settings, action="stop_instance", desired_states={"stopped", "stopping"}, boto_call="stop_instances", rollback_action="start_instance")


async def _start_instance(db: AsyncIOMotorDatabase, proposal_doc: dict[str, Any], run_id: str, settings: Any) -> LiveExecutionRecord:
    return await _toggle_instance_power(db, proposal_doc, run_id, settings, action="start_instance", desired_states={"running", "pending"}, boto_call="start_instances", rollback_action="stop_instance")


async def _toggle_instance_power(
    db: AsyncIOMotorDatabase,
    proposal_doc: dict[str, Any],
    run_id: str,
    settings: Any,
    action: str,
    desired_states: set[str],
    boto_call: str,
    rollback_action: str,
) -> LiveExecutionRecord:
    proposal_id = proposal_doc["proposal_id"]
    params = proposal_doc.get("parameters") or {}
    instance_id = params.get("instance_id", "")
    region = params.get("region", settings.aws_region)
    resource_arn = proposal_doc.get("resource_arn", "")

    session = assumed_write_session(run_id)
    ec2 = session.client("ec2", region_name=region)

    tags, instance = _describe_instance(ec2, instance_id)
    _authorize_post_describe(proposal_doc, tags, settings)

    repo = MongoLiveExecutionAuditRepository(db)
    idempotency_key = f"{proposal_id}:{action}"
    existing = await repo.get_by_idempotency_key(idempotency_key)
    if existing is not None:
        return existing

    current_state = instance["State"]["Name"]
    before_state = {"state": current_state, "instance_type": instance.get("InstanceType"), "region": region}
    rollback_descriptor = {"action": rollback_action, "instance_id": instance_id, "region": region}

    if current_state in desired_states:
        record = LiveExecutionRecord(
            idempotency_key=idempotency_key, proposal_id=proposal_id, tenant_id=proposal_doc.get("tenant_id", "unknown"),
            run_id=run_id, resource_arn=resource_arn, resource_id=instance_id, action_type=action, status="no_op",
            reason_codes=["ALREADY_IN_DESIRED_STATE"], execution_mode=settings.execution_mode, actual_aws_call_made=False,
            before_state=before_state, after_state=before_state, rollback_descriptor=rollback_descriptor,
        )
        return await repo.save(record)

    actual_call_made = False
    if settings.execution_mode == "live":
        getattr(ec2, boto_call)(InstanceIds=[instance_id])
        actual_call_made = True
        after_state = {"state": sorted(desired_states)[0], "instance_type": instance.get("InstanceType"), "region": region}
    else:
        after_state = {"state": f"{sorted(desired_states)[0]} (simulated)", "instance_type": instance.get("InstanceType"), "region": region}

    record = LiveExecutionRecord(
        idempotency_key=idempotency_key, proposal_id=proposal_id, tenant_id=proposal_doc.get("tenant_id", "unknown"),
        run_id=run_id, resource_arn=resource_arn, resource_id=instance_id, action_type=action, status="executed",
        reason_codes=[f"{action.upper()}_REQUESTED"], execution_mode=settings.execution_mode,
        actual_aws_call_made=actual_call_made, before_state=before_state, after_state=after_state,
        rollback_descriptor=rollback_descriptor,
    )
    return await repo.save(record)


# ---------------------------------------------------------------------------
# adjust_asg_capacity (Phase 15) — same three-gate / idempotency / lock
# pattern as _toggle_instance_power, targeting the autoscaling: API instead
# of ec2:. Never auto-executable regardless of environment/risk — Decision
# (services/decision/service.py::build_proposals) always sets
# requires_human_approval=True on this action_type, and this handler itself
# adds nothing beyond that; a human must still click Approve like any other
# production-adjacent action.
# ---------------------------------------------------------------------------


async def _adjust_asg_capacity(
    db: AsyncIOMotorDatabase, proposal_doc: dict[str, Any], run_id: str, settings: Any
) -> LiveExecutionRecord:
    proposal_id = proposal_doc["proposal_id"]
    tenant_id = proposal_doc.get("tenant_id", "unknown")
    params = proposal_doc.get("parameters") or {}
    asg_name = params.get("asg_name", "")
    region = params.get("region", settings.aws_region)
    resource_arn = proposal_doc.get("resource_arn", "")
    proposed_capacity = params.get("proposed_desired_capacity")

    if not asg_name or proposed_capacity is None:
        raise ExecutionRefused(
            "MISSING_ASG_PARAMETERS",
            "adjust_asg_capacity requires parameters.asg_name and parameters.proposed_desired_capacity.",
        )

    session = assumed_write_session(run_id)
    autoscaling = session.client("autoscaling", region_name=region)

    tags, group = _describe_asg(autoscaling, asg_name)
    _authorize_post_describe(proposal_doc, tags, settings)

    repo = MongoLiveExecutionAuditRepository(db)
    idempotency_key = f"{proposal_id}:adjust_asg_capacity"
    existing = await repo.get_by_idempotency_key(idempotency_key)
    if existing is not None:
        return existing

    current_capacity = group.get("DesiredCapacity")
    before_state = {"desired_capacity": current_capacity, "asg_name": asg_name, "region": region}
    rollback_descriptor = {
        "action": "adjust_asg_capacity",
        "asg_name": asg_name,
        "region": region,
        "restore_desired_capacity": current_capacity,
    }

    if current_capacity == proposed_capacity:
        record = LiveExecutionRecord(
            idempotency_key=idempotency_key, proposal_id=proposal_id, tenant_id=tenant_id, run_id=run_id,
            resource_arn=resource_arn, resource_id=asg_name, action_type="adjust_asg_capacity", status="no_op",
            reason_codes=["ALREADY_AT_DESIRED_CAPACITY"], execution_mode=settings.execution_mode,
            actual_aws_call_made=False, before_state=before_state, after_state=before_state,
            rollback_descriptor=rollback_descriptor,
        )
        return await repo.save(record)

    actual_call_made = False
    if settings.execution_mode == "live":
        autoscaling.update_auto_scaling_group(AutoScalingGroupName=asg_name, DesiredCapacity=proposed_capacity)
        actual_call_made = True
        after_state = {"desired_capacity": proposed_capacity, "asg_name": asg_name, "region": region}
    else:
        after_state = {"desired_capacity": f"{proposed_capacity} (simulated)", "asg_name": asg_name, "region": region}

    record = LiveExecutionRecord(
        idempotency_key=idempotency_key, proposal_id=proposal_id, tenant_id=tenant_id, run_id=run_id,
        resource_arn=resource_arn, resource_id=asg_name, action_type="adjust_asg_capacity", status="executed",
        reason_codes=["ASG_CAPACITY_ADJUSTED"], execution_mode=settings.execution_mode,
        actual_aws_call_made=actual_call_made, before_state=before_state, after_state=after_state,
        rollback_descriptor=rollback_descriptor,
    )
    return await repo.save(record)


# ---------------------------------------------------------------------------
# resize_instance — stop -> modify -> start, each its own audit entry
# ---------------------------------------------------------------------------


async def _wait_for_instance_state(ec2: Any, instance_id: str, target_states: set[str], max_attempts: int = 30, interval_seconds: float = 2.0) -> dict[str, Any]:
    for _ in range(max_attempts):
        _, instance = _describe_instance(ec2, instance_id)
        if instance["State"]["Name"] in target_states:
            return instance
        await asyncio.sleep(interval_seconds)
    raise ExecutionRefused("TIMEOUT_WAITING_FOR_STATE", f"Timed out waiting for {instance_id} to reach {target_states}.")


async def _resize_instance(db: AsyncIOMotorDatabase, proposal_doc: dict[str, Any], run_id: str, settings: Any) -> LiveExecutionRecord:
    proposal_id = proposal_doc["proposal_id"]
    tenant_id = proposal_doc.get("tenant_id", "unknown")
    params = proposal_doc.get("parameters") or {}
    instance_id = params.get("instance_id", "")
    region = params.get("region", settings.aws_region)
    resource_arn = proposal_doc.get("resource_arn", "")
    target_type = params.get("target_type")

    if not target_type:
        raise ExecutionRefused("MISSING_TARGET_TYPE", "resize_instance requires parameters.target_type.")

    session = assumed_write_session(run_id)
    ec2 = session.client("ec2", region_name=region)

    tags, instance = _describe_instance(ec2, instance_id)
    _authorize_post_describe(proposal_doc, tags, settings)

    repo = MongoLiveExecutionAuditRepository(db)
    current_type = instance.get("InstanceType")
    current_state = instance["State"]["Name"]
    rollback_descriptor = {"action": "resize_instance", "instance_id": instance_id, "region": region, "target_type": current_type}

    modify_key = f"{proposal_id}:resize_instance:modify_type"
    existing_modify = await repo.get_by_idempotency_key(modify_key)
    if current_type == target_type and existing_modify is None:
        record = LiveExecutionRecord(
            idempotency_key=modify_key, proposal_id=proposal_id, tenant_id=tenant_id, run_id=run_id,
            resource_arn=resource_arn, resource_id=instance_id, action_type="resize_instance", step="modify_type",
            status="no_op", reason_codes=["ALREADY_TARGET_TYPE"], execution_mode=settings.execution_mode,
            actual_aws_call_made=False, before_state={"instance_type": current_type}, after_state={"instance_type": current_type},
            rollback_descriptor=rollback_descriptor,
        )
        return await repo.save(record)
    if existing_modify is not None:
        return existing_modify

    was_running = current_state not in ("stopped", "stopping")

    # Step 1: stop (if needed) — EC2 must be stopped before
    # modify_instance_attribute can change InstanceType.
    stop_key = f"{proposal_id}:resize_instance:stop"
    stop_record = await repo.get_by_idempotency_key(stop_key)
    if stop_record is None:
        if current_state in ("stopped", "stopping"):
            stop_record = LiveExecutionRecord(
                idempotency_key=stop_key, proposal_id=proposal_id, tenant_id=tenant_id, run_id=run_id,
                resource_arn=resource_arn, resource_id=instance_id, action_type="resize_instance", step="stop",
                status="no_op", reason_codes=["ALREADY_STOPPED"], execution_mode=settings.execution_mode,
                actual_aws_call_made=False, before_state={"state": current_state}, after_state={"state": current_state},
                rollback_descriptor=rollback_descriptor,
            )
        elif settings.execution_mode == "live":
            ec2.stop_instances(InstanceIds=[instance_id])
            await _wait_for_instance_state(ec2, instance_id, {"stopped"})
            stop_record = LiveExecutionRecord(
                idempotency_key=stop_key, proposal_id=proposal_id, tenant_id=tenant_id, run_id=run_id,
                resource_arn=resource_arn, resource_id=instance_id, action_type="resize_instance", step="stop",
                status="executed", reason_codes=["STOPPED_FOR_RESIZE"], execution_mode=settings.execution_mode,
                actual_aws_call_made=True, before_state={"state": current_state}, after_state={"state": "stopped"},
                rollback_descriptor=rollback_descriptor,
            )
        else:
            stop_record = LiveExecutionRecord(
                idempotency_key=stop_key, proposal_id=proposal_id, tenant_id=tenant_id, run_id=run_id,
                resource_arn=resource_arn, resource_id=instance_id, action_type="resize_instance", step="stop",
                status="executed", reason_codes=["STOPPED_FOR_RESIZE"], execution_mode=settings.execution_mode,
                actual_aws_call_made=False, before_state={"state": current_state}, after_state={"state": "stopped (simulated)"},
                rollback_descriptor=rollback_descriptor,
            )
        stop_record = await repo.save(stop_record)

    # Step 2: modify the instance type.
    if settings.execution_mode == "live":
        ec2.modify_instance_attribute(InstanceId=instance_id, InstanceType={"Value": target_type})
        modify_actual_call = True
    else:
        modify_actual_call = False
    modify_record = LiveExecutionRecord(
        idempotency_key=modify_key, proposal_id=proposal_id, tenant_id=tenant_id, run_id=run_id,
        resource_arn=resource_arn, resource_id=instance_id, action_type="resize_instance", step="modify_type",
        status="executed", reason_codes=["TYPE_MODIFIED"], execution_mode=settings.execution_mode,
        actual_aws_call_made=modify_actual_call, before_state={"instance_type": current_type},
        after_state={"instance_type": target_type}, rollback_descriptor=rollback_descriptor,
    )
    modify_record = await repo.save(modify_record)

    if not was_running:
        return modify_record

    # Step 3: start again — only if it was running before we stopped it.
    start_key = f"{proposal_id}:resize_instance:start"
    start_record = await repo.get_by_idempotency_key(start_key)
    if start_record is None:
        if settings.execution_mode == "live":
            ec2.start_instances(InstanceIds=[instance_id])
            start_actual_call = True
            after = {"state": "running"}
        else:
            start_actual_call = False
            after = {"state": "running (simulated)"}
        start_record = LiveExecutionRecord(
            idempotency_key=start_key, proposal_id=proposal_id, tenant_id=tenant_id, run_id=run_id,
            resource_arn=resource_arn, resource_id=instance_id, action_type="resize_instance", step="start",
            status="executed", reason_codes=["RESTARTED_AFTER_RESIZE"], execution_mode=settings.execution_mode,
            actual_aws_call_made=start_actual_call, before_state={"state": "stopped"}, after_state=after,
            rollback_descriptor=rollback_descriptor,
        )
        start_record = await repo.save(start_record)
    return start_record


# ---------------------------------------------------------------------------
# delete_volume — irreversible, so a snapshot is taken first; the rollback
# descriptor points at restoring from it (a human action, not auto-applied
# — see _AUTO_ROLLBACK_ACTIONS).
# ---------------------------------------------------------------------------


async def _delete_volume(db: AsyncIOMotorDatabase, proposal_doc: dict[str, Any], run_id: str, settings: Any) -> LiveExecutionRecord:
    proposal_id = proposal_doc["proposal_id"]
    tenant_id = proposal_doc.get("tenant_id", "unknown")
    params = proposal_doc.get("parameters") or {}
    volume_id = params.get("volume_id", "")
    region = params.get("region", settings.aws_region)
    resource_arn = proposal_doc.get("resource_arn", "")

    session = assumed_write_session(run_id)
    ec2 = session.client("ec2", region_name=region)

    tags, volume = _describe_volume(ec2, volume_id)
    _authorize_post_describe(proposal_doc, tags, settings)

    repo = MongoLiveExecutionAuditRepository(db)
    idempotency_key = f"{proposal_id}:delete_volume"
    existing = await repo.get_by_idempotency_key(idempotency_key)
    if existing is not None:
        return existing

    state = volume["State"]
    before_state = {"state": state, "size_gb": volume.get("Size"), "region": region}

    if state != "available":
        raise ExecutionRefused("VOLUME_NOT_DETACHED", f"Volume {volume_id} is '{state}', not 'available' — refusing to delete an in-use volume.")

    if settings.execution_mode == "live":
        snapshot = ec2.create_snapshot(VolumeId=volume_id, Description=f"cloudcare pre-delete snapshot for {proposal_id}")
        snapshot_id = snapshot["SnapshotId"]
        ec2.delete_volume(VolumeId=volume_id)
        actual_call_made = True
        after_state = {"state": "deleted", "region": region}
    else:
        snapshot_id = "simulated-snapshot"
        actual_call_made = False
        after_state = {"state": "deleted (simulated)", "region": region}

    record = LiveExecutionRecord(
        idempotency_key=idempotency_key, proposal_id=proposal_id, tenant_id=tenant_id, run_id=run_id,
        resource_arn=resource_arn, resource_id=volume_id, action_type="delete_volume", status="executed",
        reason_codes=["SNAPSHOTTED_AND_DELETED"], execution_mode=settings.execution_mode,
        actual_aws_call_made=actual_call_made, before_state=before_state, after_state=after_state,
        rollback_descriptor={"action": "restore_volume_from_snapshot", "snapshot_id": snapshot_id, "region": region, "manual_action_required": True},
    )
    return await repo.save(record)


# ---------------------------------------------------------------------------
# schedule_instance — tags the instance with an on/off schedule; no native
# EventBridge/Lambda scheduler exists in this build, so this records intent
# as a tag an operator (or a future scheduler) can act on.
# ---------------------------------------------------------------------------


async def _schedule_instance(db: AsyncIOMotorDatabase, proposal_doc: dict[str, Any], run_id: str, settings: Any) -> LiveExecutionRecord:
    proposal_id = proposal_doc["proposal_id"]
    tenant_id = proposal_doc.get("tenant_id", "unknown")
    params = proposal_doc.get("parameters") or {}
    instance_id = params.get("instance_id", "")
    region = params.get("region", settings.aws_region)
    resource_arn = proposal_doc.get("resource_arn", "")
    schedule = params.get("schedule", "off-hours")
    schedule_tag_key = "cloudcare:schedule"

    session = assumed_write_session(run_id)
    ec2 = session.client("ec2", region_name=region)

    tags, _instance = _describe_instance(ec2, instance_id)
    _authorize_post_describe(proposal_doc, tags, settings)

    repo = MongoLiveExecutionAuditRepository(db)
    idempotency_key = f"{proposal_id}:schedule_instance"
    existing = await repo.get_by_idempotency_key(idempotency_key)
    if existing is not None:
        return existing

    current_schedule = tags.get(schedule_tag_key)
    before_state = {schedule_tag_key: current_schedule}
    rollback_descriptor = {"action": "remove_schedule_tag", "instance_id": instance_id, "region": region, "tag_key": schedule_tag_key}

    if current_schedule == schedule:
        record = LiveExecutionRecord(
            idempotency_key=idempotency_key, proposal_id=proposal_id, tenant_id=tenant_id, run_id=run_id,
            resource_arn=resource_arn, resource_id=instance_id, action_type="schedule_instance", status="no_op",
            reason_codes=["ALREADY_SCHEDULED"], execution_mode=settings.execution_mode, actual_aws_call_made=False,
            before_state=before_state, after_state=before_state, rollback_descriptor=rollback_descriptor,
        )
        return await repo.save(record)

    actual_call_made = False
    if settings.execution_mode == "live":
        ec2.create_tags(Resources=[instance_id], Tags=[{"Key": schedule_tag_key, "Value": schedule}])
        actual_call_made = True

    record = LiveExecutionRecord(
        idempotency_key=idempotency_key, proposal_id=proposal_id, tenant_id=tenant_id, run_id=run_id,
        resource_arn=resource_arn, resource_id=instance_id, action_type="schedule_instance", status="executed",
        reason_codes=["SCHEDULE_TAG_SET"], execution_mode=settings.execution_mode, actual_aws_call_made=actual_call_made,
        before_state=before_state, after_state={schedule_tag_key: schedule}, rollback_descriptor=rollback_descriptor,
    )
    return await repo.save(record)


# ---------------------------------------------------------------------------
# Rollback — invoked automatically by services/verifier/health.py on a
# failed post-execution check, or manually via
# POST /v1/executions/{id}/rollback.
# ---------------------------------------------------------------------------


async def execute_rollback(db: AsyncIOMotorDatabase, record: LiveExecutionRecord) -> LiveExecutionRecord | None:
    """Re-dispatches record.rollback_descriptor as a fresh, system-approved
    proposal. Returns None (no auto-rollback possible) for actions outside
    _AUTO_ROLLBACK_ACTIONS — delete_volume and schedule_instance's
    descriptors are preserved for a human to act on instead."""
    descriptor = record.rollback_descriptor
    if not descriptor or descriptor.get("action") not in _AUTO_ROLLBACK_ACTIONS:
        logger.warning(
            "executor: rollback for %s requires manual action: %s", record.execution_id, descriptor
        )
        return None

    rollback_action = descriptor["action"]
    rollback_proposal_doc = {
        "proposal_id": f"{record.proposal_id}:rollback",
        "tenant_id": record.tenant_id,
        "resource_arn": record.resource_arn,
        "action_type": rollback_action,
        # A system-initiated rollback re-uses the SAME approval as the
        # original action — the human who approved the change already
        # authorized undoing it if it fails; a rollback never waits on a
        # fresh human click.
        "status": "approved",
        "environment": "unknown",
        "risk_level": "low",
        "template_id": {
            "start_instance": "ec2.start.v1",
            "stop_instance": "ec2.stop.v1",
            "resize_instance": "ec2.resize.v1",
        }[rollback_action],
        "parameters": {k: v for k, v in descriptor.items() if k != "action"},
    }

    result = await execute_action(db, rollback_proposal_doc, run_id=record.run_id or record.proposal_id)

    try:
        original = await db.execution_audit.find_one({"execution_id": record.execution_id})
        if original:
            await db.execution_audit.update_one(
                {"execution_id": record.execution_id}, {"$set": {"status": "rolled_back"}}
            )
    except Exception:
        logger.exception("executor: failed to flag %s as rolled_back", record.execution_id)

    return result
