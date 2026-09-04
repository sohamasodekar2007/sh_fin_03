from __future__ import annotations

import asyncio
import logging
import time
from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, Query
from motor.motor_asyncio import AsyncIOMotorDatabase
from pydantic import BaseModel

from apps.api.config import get_settings
from apps.api.db import get_db
from apps.api.dependencies import CurrentUser, get_current_user
from packages.aws.session import AWSClientFactory
from packages.schemas.execution import LiveExecutionRecord
from services.collector.collector_service import AWSCollectorService
from services.executor.actions import ExecutionRefused, assumed_write_session
from services.executor.execution_audit import MongoLiveExecutionAuditRepository
from services.scheduler import run_pipeline_for_account

router = APIRouter(prefix="/v1/agent-command", tags=["agent-command"])
logger = logging.getLogger(__name__)

_COLLECTION = "agent_command_runs"
_LATEST_COMMAND_CACHE: dict[str, dict[str, Any]] = {}
_MONGO_UNAVAILABLE_UNTIL = 0.0
_MONGO_RECHECK_SECONDS = 5.0


class StopInstanceRequest(BaseModel):
    confirm: bool = False


def _tags_to_dict(tags: list[dict[str, Any]] | None) -> dict[str, str]:
    return {str(tag.get("Key")): str(tag.get("Value", "")) for tag in tags or [] if tag.get("Key")}


def _instance_summary(instance: dict[str, Any]) -> dict[str, Any]:
    tags = _tags_to_dict(instance.get("Tags"))
    return {
        "instance_id": instance["InstanceId"],
        "name": tags.get("Name"),
        "state": instance.get("State", {}).get("Name", "unknown"),
        "instance_type": instance.get("InstanceType"),
        "availability_zone": (instance.get("Placement") or {}).get("AvailabilityZone"),
        "region": (instance.get("Placement") or {}).get("AvailabilityZone", "")[:-1],
        "tags": tags,
    }


def _resource_from_instance_summary(instance: dict[str, Any]) -> dict[str, Any]:
    return {
        "resource_id": instance["instance_id"],
        "resource_type": "ec2_instance",
        "instance_type": instance.get("instance_type"),
        "name": instance.get("name") or instance["instance_id"],
        "region": instance.get("region"),
        "availability_zone": instance.get("availability_zone"),
        "state": instance.get("state"),
        "environment": (instance.get("tags") or {}).get("Environment") or "unknown",
        "tags": instance.get("tags") or {},
    }


def _empty_agent_command_doc(settings) -> dict[str, Any]:
    return {
        "run_id": None,
        "status": "empty",
        "provider": "aws",
        "account_id": settings.aws_account_id or "demo-account",
        "region": settings.aws_region,
        "model_router": _public_base_url(settings),
        "decision_model": settings.openai_model,
        "focus_dataset_id": None,
        "focus_version": settings.focus_version,
        "focus_source": "waiting",
        "focus_row_count": 0,
        "summary": {
            "resources": 0,
            "findings": 0,
            "proposals": 0,
            "focus_rows": 0,
            "pending_approvals": 0,
            "blocked": 0,
            "potential_monthly_savings": 0,
            "executions_total": 0,
            "executed_or_simulated": 0,
            "blocked_or_refused": 0,
        },
        "steps": [],
        "chart": [],
        "proposals": [],
        "executions": [],
    }


def _public_agent_command_doc(doc: dict[str, Any]) -> dict[str, Any]:
    public = dict(doc)
    public.pop("_id", None)
    public.pop("tenant_id", None)
    public.pop("raw_pipeline", None)
    return public


def _fallback_pipeline_result_from_instances(
    *,
    instances: list[dict[str, Any]],
    run_id: str | None,
    provider: str,
    account_id: str,
    region: str,
    error: str | None = None,
) -> dict[str, Any]:
    resources = [_resource_from_instance_summary(instance) for instance in instances]
    monitor = {
        "status": "success" if error is None else "degraded",
        "agent": "Monitor Agent (Observe)",
        "run_id": run_id,
        "provider": provider,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "account_id": account_id,
        "region": region,
        "observation": {
            "account_id": account_id,
            "region": region,
            "status": "success" if error is None else "degraded",
            "resource_count": len(resources),
            "metric_count": 0,
            "cost_day_count": 0,
            "resources": resources,
            "cpu_metrics": [],
            "daily_costs": [],
            "issues": ([{"source": "mongodb", "message": error, "retryable": True}] if error else []),
        },
        "focus_dataset_id": None,
        "focus_version": get_settings().focus_version,
        "row_count": 0,
        "resource_count": len(resources),
        "source": "live",
        "summary": {
            "total_resources": len(resources),
            "metrics_collected": 0,
            "cost_days_collected": 0,
            "idle_instances_detected": 0,
            "oversized_instances_detected": 0,
            "unattached_ebs_volumes_detected": 0,
            "proposals_resurfaced": 0,
        },
    }
    return {
        "run_id": run_id,
        "provider": provider,
        "monitor": monitor,
        "analyzer": {
            "status": "degraded" if error else "success",
            "findings_count": 0,
            "summary": {},
        },
        "decision": {
            "status": "degraded" if error else "success",
            "proposals_count": 0,
            "proposals": [],
            "llm_used": False,
        },
        "supervisor": {
            "status": "degraded" if error else "success",
            "summary": {"total": 0},
        },
    }


def _fallback_agent_command_doc(
    *,
    settings,
    instances: list[dict[str, Any]],
    run_id: str | None,
    status: str,
    error: str | None,
) -> dict[str, Any]:
    provider = "aws"
    account_id = settings.aws_account_id or "demo-account"
    region = settings.aws_region
    pipeline_result = _fallback_pipeline_result_from_instances(
        instances=instances,
        run_id=run_id,
        provider=provider,
        account_id=account_id,
        region=region,
        error=error,
    )
    focus_meta = _focus_metadata(pipeline_result)
    doc = {
        "run_id": run_id,
        "status": status,
        "provider": provider,
        "account_id": account_id,
        "region": region,
        "model_router": _public_base_url(settings),
        "decision_model": settings.openai_model,
        **focus_meta,
        "summary": {
            "resources": len(instances),
            "findings": 0,
            "proposals": 0,
            "focus_rows": focus_meta["focus_row_count"],
            "pending_approvals": 0,
            "blocked": 0,
            "potential_monthly_savings": 0,
            **_execution_summary([]),
        },
        "steps": _build_steps(
            pipeline_result=pipeline_result,
            proposals=[],
            executions=[],
            settings=settings,
        ),
        "chart": _chart_from_proposals([]),
        "proposals": [],
        "executions": [],
    }
    if error:
        doc["persistence_error"] = error
    return doc


def _live_aws_agent_command_doc(
    *,
    settings,
    run_id: str | None,
    status: str,
    error: str | None,
) -> dict[str, Any]:
    account_id = settings.aws_account_id or "demo-account"
    region = settings.aws_region
    try:
        snapshot = AWSCollectorService(
            client_factory=AWSClientFactory(settings),
            region=region,
            account_id=account_id,
        ).collect_snapshot()
        snapshot_data = snapshot.model_dump(mode="json")
        resources_count = int(snapshot_data.get("resource_count") or len(snapshot_data.get("resources") or []))
        issues = snapshot_data.get("issues") or []
    except Exception as exc:  # noqa: BLE001 - EC2 inventory is still useful if a broad collector fails
        logger.exception("agent-command: full AWS fallback failed; using EC2-only fallback")
        instances = _list_ec2_instance_summaries(region)
        return _fallback_agent_command_doc(
            settings=settings,
            instances=instances,
            run_id=run_id,
            status=status,
            error=error or str(exc),
        )

    monitor = {
        "status": status,
        "agent": "Monitor Agent (Observe)",
        "run_id": run_id,
        "provider": "aws",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "account_id": account_id,
        "region": region,
        "observation": snapshot_data,
        "focus_dataset_id": None,
        "focus_version": settings.focus_version,
        "row_count": 0,
        "resource_count": resources_count,
        "source": "live",
        "summary": {
            "total_resources": resources_count,
            "metrics_collected": snapshot_data.get("metric_count", 0),
            "cost_days_collected": snapshot_data.get("cost_day_count", 0),
            "idle_instances_detected": 0,
            "oversized_instances_detected": 0,
            "unattached_ebs_volumes_detected": sum(
                1
                for resource in snapshot_data.get("resources") or []
                if resource.get("resource_type") == "ebs_volume" and resource.get("state") == "available"
            ),
            "proposals_resurfaced": 0,
            "collector_issues": len(issues),
        },
    }
    pipeline_result = {
        "run_id": run_id,
        "provider": "aws",
        "monitor": monitor,
        "analyzer": {"status": status, "findings_count": 0, "summary": {}},
        "decision": {"status": status, "proposals_count": 0, "proposals": [], "llm_used": False},
        "supervisor": {"status": status, "summary": {"total": 0}},
    }
    focus_meta = _focus_metadata(pipeline_result)
    doc = {
        "run_id": run_id,
        "status": status,
        "provider": "aws",
        "account_id": account_id,
        "region": region,
        "model_router": _public_base_url(settings),
        "decision_model": settings.openai_model,
        **focus_meta,
        "summary": {
            "resources": resources_count,
            "findings": 0,
            "proposals": 0,
            "focus_rows": 0,
            "pending_approvals": 0,
            "blocked": 0,
            "potential_monthly_savings": 0,
            **_execution_summary([]),
        },
        "steps": _build_steps(
            pipeline_result=pipeline_result,
            proposals=[],
            executions=[],
            settings=settings,
        ),
        "chart": _chart_from_proposals([]),
        "proposals": [],
        "executions": [],
    }
    if error:
        doc["persistence_error"] = error
    return doc


async def _log_manual_stop(
    db: AsyncIOMotorDatabase,
    tenant_id: str,
    run_id: str,
    record: LiveExecutionRecord,
    started_at: datetime,
) -> None:
    finished_at = datetime.now(timezone.utc)
    await db.agent_runs.insert_one(
        {
            "log_id": str(uuid4()),
            "tenant_id": tenant_id,
            "run_id": run_id,
            "agent": "Executor",
            "status": "success" if record.status in {"executed", "no_op"} else "failed",
            "started_at": started_at,
            "finished_at": finished_at,
            "duration_ms": int((finished_at - started_at).total_seconds() * 1000),
            "input_summary": {
                "proposal_id": record.proposal_id,
                "resource_arn": record.resource_arn,
                "action_type": "stop_instance",
                "source": "agent_command_manual",
            },
            "output_summary": {
                "message": (
                    f"Executor {record.status}: stop_instance on {record.resource_id}"
                    + (f" ({', '.join(record.reason_codes)})" if record.reason_codes else "")
                ),
                "execution_status": record.status,
                "reason_codes": record.reason_codes,
                "actual_aws_call_made": record.actual_aws_call_made,
                "execution_mode": record.execution_mode,
            },
            "payload": record.model_dump(mode="json"),
            "error": None if record.status in {"executed", "no_op"} else "; ".join(record.reason_codes),
        }
    )


async def ensure_agent_command_indexes(db: AsyncIOMotorDatabase) -> None:
    await db[_COLLECTION].create_index([("tenant_id", 1), ("created_at", -1)], name="tenant_created")
    await db[_COLLECTION].create_index([("tenant_id", 1), ("run_id", 1)], unique=True, name="tenant_run_unique")


async def _mongo_available(db: AsyncIOMotorDatabase, timeout_seconds: float = 1.5) -> bool:
    global _MONGO_UNAVAILABLE_UNTIL
    now = time.monotonic()
    if now < _MONGO_UNAVAILABLE_UNTIL:
        return False
    try:
        await asyncio.wait_for(db.client.admin.command("ping"), timeout=timeout_seconds)
        _MONGO_UNAVAILABLE_UNTIL = 0.0
        return True
    except Exception:
        _MONGO_UNAVAILABLE_UNTIL = time.monotonic() + _MONGO_RECHECK_SECONDS
        return False


def _agent_step(
    key: str,
    name: str,
    role: str,
    status: str,
    summary: str,
    metrics: list[dict[str, Any]],
    artifacts: list[str],
) -> dict[str, Any]:
    return {
        "key": key,
        "name": name,
        "role": role,
        "status": status,
        "summary": summary,
        "metrics": metrics,
        "artifacts": artifacts,
    }


def _money(value: Any) -> float:
    try:
        return round(float(value), 2)
    except (TypeError, ValueError):
        return 0.0


def _proposal_savings(proposals: list[dict[str, Any]]) -> float:
    return round(sum(_money(p.get("expected_monthly_savings")) for p in proposals), 2)


def _execution_summary(executions: list[dict[str, Any]]) -> dict[str, Any]:
    executed = [e for e in executions if e.get("status") in {"executed", "no_op", "simulated"}]
    blocked = [e for e in executions if e.get("status") in {"blocked", "refused", "failed", "rejected"}]
    return {
        "executions_total": len(executions),
        "executed_or_simulated": len(executed),
        "blocked_or_refused": len(blocked),
    }


def _focus_metadata(pipeline_result: dict[str, Any]) -> dict[str, Any]:
    monitor = pipeline_result.get("monitor") or {}
    return {
        "focus_dataset_id": monitor.get("focus_dataset_id"),
        "focus_version": monitor.get("focus_version") or getattr(get_settings(), "focus_version", "1.2"),
        "focus_source": monitor.get("source", "sample"),
        "focus_row_count": monitor.get("row_count", 0),
    }


def _resource_ids_from_pipeline(pipeline_result: dict[str, Any]) -> set[str]:
    analyzer = pipeline_result.get("analyzer") or {}
    findings = analyzer.get("findings") or []
    resource_ids = {str(f.get("resource_id")) for f in findings if f.get("resource_id")}
    if resource_ids:
        return resource_ids

    monitor = pipeline_result.get("monitor") or {}
    resources = ((monitor.get("observation") or {}).get("resources")) or []
    return {
        str(r.get("resource_id") or r.get("instance_id") or r.get("id"))
        for r in resources
        if r.get("resource_id") or r.get("instance_id") or r.get("id")
    }


def _proposal_matches_resource(proposal: dict[str, Any], resource_ids: set[str]) -> bool:
    instance_id = (proposal.get("parameters") or {}).get("instance_id")
    if instance_id and str(instance_id) in resource_ids:
        return True
    resource_arn = str(proposal.get("resource_arn") or "")
    return any(resource_id and resource_id in resource_arn for resource_id in resource_ids)


def _proposal_sort_value(proposal: dict[str, Any]) -> tuple[int, str]:
    status_rank = {
        "verified": 6,
        "executed": 5,
        "approved": 4,
        "pending_approval": 3,
        "proposed": 2,
        "blocked": 1,
        "rejected": 0,
    }
    timestamp = (
        proposal.get("approved_at")
        or proposal.get("updated_at")
        or proposal.get("created_at")
        or proposal.get("proposal_id")
        or ""
    )
    return status_rank.get(str(proposal.get("status")), -1), str(timestamp)


def _dedupe_proposals(proposals: list[dict[str, Any]]) -> list[dict[str, Any]]:
    by_resource_action: dict[tuple[str, str], dict[str, Any]] = {}
    for proposal in proposals:
        key = (str(proposal.get("resource_arn") or ""), str(proposal.get("action_type") or ""))
        existing = by_resource_action.get(key)
        if existing is None or _proposal_sort_value(proposal) > _proposal_sort_value(existing):
            by_resource_action[key] = proposal
    return list(by_resource_action.values())


async def _active_proposals_for_pipeline(
    db: AsyncIOMotorDatabase,
    tenant_id: str,
    pipeline_result: dict[str, Any],
) -> list[dict[str, Any]]:
    resource_ids = _resource_ids_from_pipeline(pipeline_result)
    if not resource_ids:
        return []

    docs = await db.proposals.find(
        {
            "tenant_id": tenant_id,
            "status": {"$in": ["proposed", "pending_approval", "approved", "blocked"]},
        },
        {"_id": 0},
    ).sort("approved_at", -1).to_list(length=100)

    matching = [doc for doc in docs if _proposal_matches_resource(doc, resource_ids)]
    matching = _dedupe_proposals(matching)
    matching.sort(key=lambda p: (_money(p.get("expected_monthly_savings")), p.get("proposal_id", "")), reverse=True)
    return matching


async def _executions_for_proposals(
    db: AsyncIOMotorDatabase,
    tenant_id: str,
    proposal_ids: list[str],
) -> list[dict[str, Any]]:
    if not proposal_ids:
        return []
    docs = await db.execution_audit.find(
        {"tenant_id": tenant_id, "proposal_id": {"$in": proposal_ids}},
        {"_id": 0},
    ).sort("started_at", -1).to_list(length=None)
    return docs


def _build_steps(
    *,
    pipeline_result: dict[str, Any],
    proposals: list[dict[str, Any]],
    executions: list[dict[str, Any]],
    settings,
) -> list[dict[str, Any]]:
    monitor = pipeline_result.get("monitor") or {}
    analyzer = pipeline_result.get("analyzer") or {}
    decision = pipeline_result.get("decision") or {}
    supervisor = pipeline_result.get("supervisor") or {}
    monitor_summary = monitor.get("summary") or {}
    focus_meta = _focus_metadata(pipeline_result)
    analyzer_summary = analyzer.get("summary") or {}
    supervisor_summary = supervisor.get("summary") or {}
    execution_counts = _execution_summary(executions)

    pending = [p for p in proposals if p.get("status") == "pending_approval"]
    blocked = [p for p in proposals if p.get("status") == "blocked"]
    new_proposals_count = int(decision.get("proposals_count") or 0)
    active_proposals_count = len(proposals)
    decision_summary = (
        f"Built {new_proposals_count} new proposals and surfaced {active_proposals_count} active MongoDB proposals."
        if active_proposals_count and new_proposals_count != active_proposals_count
        else f"Built {active_proposals_count} action proposals with deterministic action templates."
    )
    supervisor_total = max(int(supervisor_summary.get("total") or 0), active_proposals_count)

    return [
        _agent_step(
            "monitor",
            "Monitor Agent v2",
            "Multi-cloud ingestion",
            monitor.get("status", "success"),
            (
                f"Normalized {monitor.get('resource_count', monitor_summary.get('total_resources', 0))} resources "
                f"into FOCUS {focus_meta['focus_version']} from {focus_meta['focus_source']}."
            ),
            [
                {"label": "Resources", "value": monitor_summary.get("total_resources", 0)},
                {"label": "FOCUS", "value": focus_meta["focus_version"]},
                {"label": "Rows", "value": focus_meta["focus_row_count"]},
            ],
            ["cloud_snapshots", "focus_datasets", "resources", "resource_metrics"],
        ),
        _agent_step(
            "analyzer",
            "Analyzer Agent",
            "Detection and ML-style anomaly scoring",
            analyzer.get("status", "success"),
            f"Produced {analyzer.get('findings_count', 0)} findings across compute, storage, and spend signals.",
            [
                {"label": "Findings", "value": analyzer.get("findings_count", 0)},
                {"label": "Idle", "value": analyzer_summary.get("idle_ec2_findings", 0)},
                {"label": "Spend spikes", "value": analyzer_summary.get("spend_anomaly_findings", 0)},
            ],
            ["analyzer_findings", "agent_runs"],
        ),
        _agent_step(
            "decision",
            "Decision Agent",
            "Structured LLM reasoning",
            "success" if decision.get("status") == "success" else decision.get("status", "success"),
            decision_summary,
            [
                {"label": "Model", "value": settings.openai_model},
                {"label": "LLM used", "value": "yes" if decision.get("llm_used") else "fallback"},
                {"label": "Potential/mo", "value": _proposal_savings(proposals), "format": "usd"},
            ],
            ["decision_proposals", "proposals", "llm_calls"],
        ),
        _agent_step(
            "supervisor",
            "Supervisor Agent",
            "Risk, policy, and HITL routing",
            supervisor.get("status", "success"),
            f"Routed {len(pending)} proposals to human review and blocked {len(blocked)}.",
            [
                {"label": "Pending", "value": len(pending)},
                {"label": "Blocked", "value": len(blocked)},
                {"label": "Reviews", "value": supervisor_total},
            ],
            ["supervisor_reviews", "approval_nonces", "proposals"],
        ),
        _agent_step(
            "executor",
            "Executor Agent",
            "Guarded simulation/live execution",
            "ready" if pending else "standing_by",
            f"{len(pending)} approvals are ready for execution; {execution_counts['executed_or_simulated']} actions already executed or simulated.",
            [
                {"label": "Mode", "value": settings.execution_mode},
                {"label": "Enabled", "value": "yes" if settings.execution_enabled else "simulation guard"},
                {"label": "Completed", "value": execution_counts["executed_or_simulated"]},
            ],
            ["execution_audit", "proposals"],
        ),
    ]


def _chart_from_proposals(proposals: list[dict[str, Any]]) -> list[dict[str, Any]]:
    total = _proposal_savings(proposals)
    pending = _proposal_savings([p for p in proposals if p.get("status") == "pending_approval"])
    approved = _proposal_savings([p for p in proposals if p.get("status") in {"approved", "executed", "verified"}])
    blocked = _proposal_savings([p for p in proposals if p.get("status") == "blocked"])
    return [
        {"stage": "Detected", "savings": total},
        {"stage": "Routed", "savings": pending + approved},
        {"stage": "Approved", "savings": approved},
        {"stage": "Blocked", "savings": blocked},
    ]


def _public_base_url(settings) -> str:
    return str(settings.openai_base_url).replace("https://", "").replace("/v1", "")


def _list_ec2_instance_summaries(region: str, state: str | None = None) -> list[dict[str, Any]]:
    session = assumed_write_session("agent-command-list-ec2")
    ec2 = session.client("ec2", region_name=region)
    filters = [{"Name": "instance-state-name", "Values": [state]}] if state else []
    resp = ec2.describe_instances(Filters=filters)

    instances: list[dict[str, Any]] = []
    for reservation in resp.get("Reservations", []):
        for instance in reservation.get("Instances", []):
            instances.append(_instance_summary(instance))
    instances.sort(key=lambda item: (item["state"] != "running", item.get("name") or "", item["instance_id"]))
    return instances


@router.get("/ec2-instances", response_model=list[dict[str, Any]])
async def list_ec2_instances(
    current_user: CurrentUser,
    state: str | None = Query(default=None),
    region: str | None = Query(default=None),
) -> list[dict[str, Any]]:
    settings = get_settings()
    region = region or settings.aws_region

    try:
        return _list_ec2_instance_summaries(region, state)
    except ExecutionRefused as exc:
        raise HTTPException(status_code=400, detail=exc.message) from exc
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Could not list EC2 instances: {exc}") from exc


@router.post("/ec2-instances/{instance_id}/stop", response_model=dict[str, Any])
async def stop_ec2_instance(
    instance_id: str,
    body: StopInstanceRequest,
    current_user: CurrentUser,
    region: str | None = Query(default=None),
) -> dict[str, Any]:
    if not body.confirm:
        raise HTTPException(status_code=400, detail="Human confirmation is required before stopping an instance.")

    db = get_db()
    settings = get_settings()
    if not settings.execution_enabled:
        raise HTTPException(status_code=400, detail="EXECUTION_ENABLED is false; refusing to stop instances.")

    tenant_id = current_user["tenant_id"]
    region = region or settings.aws_region
    run_id = f"manual-stop-{uuid4()}"
    proposal_id = f"{run_id}:{instance_id}"
    resource_arn = f"arn:aws:ec2:{region}:{settings.aws_account_id or 'unknown'}:instance/{instance_id}"
    started_at = datetime.now(timezone.utc)

    try:
        session = assumed_write_session(run_id)
        ec2 = session.client("ec2", region_name=region)
        before_resp = ec2.describe_instances(InstanceIds=[instance_id])
        before_instance = before_resp["Reservations"][0]["Instances"][0]
        before = _instance_summary(before_instance)

        if before["state"] == "stopped":
            record = LiveExecutionRecord(
                idempotency_key=f"{proposal_id}:stop_instance",
                proposal_id=proposal_id,
                tenant_id=tenant_id,
                run_id=run_id,
                resource_arn=resource_arn,
                resource_id=instance_id,
                action_type="stop_instance",
                status="no_op",
                reason_codes=["ALREADY_STOPPED"],
                execution_mode=settings.execution_mode,
                actual_aws_call_made=False,
                before_state=before,
                after_state=before,
                rollback_descriptor={"action": "start_instance", "instance_id": instance_id, "region": region},
            )
        else:
            actual_call_made = False
            if settings.execution_mode == "live":
                ec2.stop_instances(InstanceIds=[instance_id])
                actual_call_made = True
                waiter = ec2.get_waiter("instance_stopped")
                waiter.wait(
                    InstanceIds=[instance_id],
                    WaiterConfig={"Delay": 3, "MaxAttempts": 20},
                )

            after_resp = ec2.describe_instances(InstanceIds=[instance_id])
            after_instance = after_resp["Reservations"][0]["Instances"][0]
            after = _instance_summary(after_instance)
            if settings.execution_mode != "live":
                after["state"] = "stopped (simulated)"

            record = LiveExecutionRecord(
                idempotency_key=f"{proposal_id}:stop_instance",
                proposal_id=proposal_id,
                tenant_id=tenant_id,
                run_id=run_id,
                resource_arn=resource_arn,
                resource_id=instance_id,
                action_type="stop_instance",
                status="executed",
                reason_codes=["STOP_INSTANCE_REQUESTED"],
                execution_mode=settings.execution_mode,
                actual_aws_call_made=actual_call_made,
                before_state=before,
                after_state=after,
                rollback_descriptor={"action": "start_instance", "instance_id": instance_id, "region": region},
            )

        persistence_error: str | None = None
        try:
            record = await MongoLiveExecutionAuditRepository(db).save(record)
            await _log_manual_stop(db, tenant_id, run_id, record, started_at)
            await db.resources.update_one(
                {"tenant_id": tenant_id, "id": instance_id},
                {
                    "$set": {
                        "state": record.after_state.get("state"),
                        "status": "At-risk" if record.after_state.get("state") != "running" else "Healthy",
                        "provider": "aws",
                    }
                },
            )
        except Exception as exc:  # noqa: BLE001 - EC2 outcome should still be visible if logging is down
            persistence_error = str(exc)
            logger.exception("agent-command: failed to persist manual stop result for %s", instance_id)
        return {
            "execution": record.model_dump(mode="json"),
            "instance": record.after_state,
            "persistence_error": persistence_error,
        }
    except ExecutionRefused as exc:
        raise HTTPException(status_code=400, detail=exc.message) from exc
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Could not stop EC2 instance {instance_id}: {exc}") from exc


async def _freshen_saved_doc(
    db: AsyncIOMotorDatabase,
    tenant_id: str,
    doc: dict[str, Any],
) -> dict[str, Any]:
    settings = get_settings()
    proposals = doc.get("proposals") or []

    if not proposals and doc.get("raw_pipeline"):
        proposals = await _active_proposals_for_pipeline(db, tenant_id, doc["raw_pipeline"])

    proposal_ids = [p["proposal_id"] for p in proposals if p.get("proposal_id")]

    if proposal_ids:
        latest_proposals = await db.proposals.find(
            {"tenant_id": tenant_id, "proposal_id": {"$in": proposal_ids}},
            {"_id": 0},
        ).to_list(length=None)
        by_id = {p["proposal_id"]: p for p in latest_proposals}
        proposals = [by_id.get(p.get("proposal_id"), p) for p in proposals]
        proposals = _dedupe_proposals(proposals)
        proposal_ids = [p["proposal_id"] for p in proposals if p.get("proposal_id")]

    executions = await _executions_for_proposals(db, tenant_id, proposal_ids)
    focus_meta = _focus_metadata(doc.get("raw_pipeline") or {})
    doc["proposals"] = proposals
    doc["executions"] = executions
    doc["chart"] = _chart_from_proposals(proposals)
    doc["focus_dataset_id"] = doc.get("focus_dataset_id") or focus_meta["focus_dataset_id"]
    doc["focus_version"] = doc.get("focus_version") or focus_meta["focus_version"]
    doc["focus_source"] = doc.get("focus_source") or focus_meta["focus_source"]
    doc["focus_row_count"] = doc.get("focus_row_count") or focus_meta["focus_row_count"]
    doc["summary"] = {
        **(doc.get("summary") or {}),
        "focus_rows": doc["focus_row_count"],
        "proposals": len(proposals),
        "pending_approvals": sum(1 for p in proposals if p.get("status") == "pending_approval"),
        "blocked": sum(1 for p in proposals if p.get("status") == "blocked"),
        "potential_monthly_savings": _proposal_savings(proposals),
        **_execution_summary(executions),
    }
    doc["steps"] = _build_steps(
        pipeline_result=doc.get("raw_pipeline") or {},
        proposals=proposals,
        executions=executions,
        settings=settings,
    )
    doc.pop("_id", None)
    doc.pop("tenant_id", None)
    doc.pop("raw_pipeline", None)
    return doc


@router.post("/run", response_model=dict[str, Any])
async def run_agent_command(
    current_user: CurrentUser,
    provider: str | None = Query(default="aws"),
    account_id: str | None = Query(default=None),
    region: str | None = Query(default=None),
) -> dict[str, Any]:
    db = get_db()
    settings = get_settings()
    tenant_id = current_user["tenant_id"]
    provider = (provider or "aws").strip().lower()
    run_id = str(uuid4())
    started_at = datetime.now(timezone.utc)

    if provider == "aws":
        account_id = account_id or settings.aws_account_id or "demo-account"
        region = region or settings.aws_region
    elif provider == "azure":
        account_id = account_id or settings.azure_subscription_id or "demo-subscription"
        region = region or "global"
    elif provider == "vps":
        account_id = account_id or settings.vps_host or "vps-not-configured"
        region = region or "on-premises"
    else:
        account_id = account_id or "demo-account"
        region = region or settings.aws_region

    status = "success"
    persistence_error: str | None = None
    mongo_available = await _mongo_available(db)
    if provider == "aws" and not mongo_available:
        persistence_error = "MongoDB is unavailable; showing live AWS inventory without persisted pipeline artifacts."
        public_doc = _live_aws_agent_command_doc(
            settings=settings,
            run_id=run_id,
            status="degraded",
            error=persistence_error,
        )
        _LATEST_COMMAND_CACHE[tenant_id] = public_doc
        return public_doc

    try:
        pipeline_result = await run_pipeline_for_account(tenant_id, provider, account_id, region, run_id=run_id)
    except Exception as exc:  # noqa: BLE001 - keep live AWS inventory visible if Mongo-backed stages are down
        status = "degraded"
        persistence_error = str(exc)
        logger.exception("agent-command: pipeline failed; returning live AWS fallback for %s", run_id)
        if provider == "aws":
            instances = _list_ec2_instance_summaries(region)
            pipeline_result = _fallback_pipeline_result_from_instances(
                instances=instances,
                run_id=run_id,
                provider=provider,
                account_id=account_id,
                region=region,
                error=persistence_error,
            )
        else:
            raise

    proposals = (pipeline_result.get("decision") or {}).get("proposals") or []
    if not proposals:
        try:
            proposals = await _active_proposals_for_pipeline(db, tenant_id, pipeline_result)
        except Exception as exc:  # noqa: BLE001 - proposals are DB-backed; inventory should still render
            persistence_error = persistence_error or str(exc)
            logger.exception("agent-command: failed to load active proposals for %s", run_id)
            proposals = []
    proposal_ids = [p["proposal_id"] for p in proposals if p.get("proposal_id")]
    try:
        executions = await _executions_for_proposals(db, tenant_id, proposal_ids)
    except Exception as exc:  # noqa: BLE001 - executions are DB-backed; inventory should still render
        persistence_error = persistence_error or str(exc)
        logger.exception("agent-command: failed to load executions for %s", run_id)
        executions = []
    focus_meta = _focus_metadata(pipeline_result)

    doc = {
        "run_id": run_id,
        "tenant_id": tenant_id,
        "created_at": started_at,
        "finished_at": datetime.now(timezone.utc),
        "provider": provider,
        "account_id": account_id,
        "region": region,
        "status": status,
        "model_router": _public_base_url(settings),
        "decision_model": settings.openai_model,
        **focus_meta,
        "summary": {
            "resources": (pipeline_result.get("monitor") or {}).get("resource_count", 0),
            "findings": (pipeline_result.get("analyzer") or {}).get("findings_count", 0),
            "proposals": len(proposals),
            "focus_rows": focus_meta["focus_row_count"],
            "pending_approvals": sum(1 for p in proposals if p.get("status") == "pending_approval"),
            "blocked": sum(1 for p in proposals if p.get("status") == "blocked"),
            "potential_monthly_savings": _proposal_savings(proposals),
            **_execution_summary(executions),
        },
        "steps": _build_steps(
            pipeline_result=pipeline_result,
            proposals=proposals,
            executions=executions,
            settings=settings,
        ),
        "chart": _chart_from_proposals(proposals),
        "proposals": proposals,
        "executions": executions,
        "raw_pipeline": pipeline_result,
    }
    if persistence_error:
        doc["persistence_error"] = persistence_error

    public_doc = _public_agent_command_doc(doc)
    _LATEST_COMMAND_CACHE[tenant_id] = public_doc
    try:
        await db[_COLLECTION].update_one(
            {"tenant_id": tenant_id, "run_id": run_id},
            {"$set": doc},
            upsert=True,
        )
        public_doc = await _freshen_saved_doc(db, tenant_id, doc)
        _LATEST_COMMAND_CACHE[tenant_id] = public_doc
        return public_doc
    except Exception as exc:  # noqa: BLE001 - Mongo persistence should not erase live AWS collection output
        public_doc["persistence_error"] = public_doc.get("persistence_error") or str(exc)
        logger.exception("agent-command: failed to persist/freshen run %s", run_id)
        return public_doc


@router.get("/latest", response_model=dict[str, Any])
async def latest_agent_command(current_user: CurrentUser) -> dict[str, Any]:
    db = get_db()
    settings = get_settings()
    tenant_id = current_user["tenant_id"]
    if not await _mongo_available(db):
        cached = _LATEST_COMMAND_CACHE.get(tenant_id)
        if cached:
            if cached.get("status") == "success":
                return cached
            return {
                **cached,
                "persistence_error": cached.get("persistence_error")
                or "MongoDB is unavailable; returning the last live AWS snapshot kept in memory.",
            }
        try:
            doc = _live_aws_agent_command_doc(
                settings=settings,
                run_id=None,
                status="degraded",
                error="MongoDB is unavailable; showing live AWS inventory without persisted pipeline artifacts.",
            )
            _LATEST_COMMAND_CACHE[tenant_id] = doc
            return doc
        except Exception as fallback_exc:
            logger.exception("agent-command: live AWS latest fallback failed for %s", tenant_id)
            return {**_empty_agent_command_doc(settings), "status": "error", "persistence_error": str(fallback_exc)}

    try:
        doc = await db[_COLLECTION].find_one({"tenant_id": tenant_id}, sort=[("created_at", -1)])
        if doc:
            public_doc = await _freshen_saved_doc(db, tenant_id, doc)
            _LATEST_COMMAND_CACHE[tenant_id] = public_doc
            return public_doc
    except Exception as exc:  # noqa: BLE001 - keep the dashboard usable when Mongo DNS is down
        logger.exception("agent-command: failed to read latest run for %s", tenant_id)
        cached = _LATEST_COMMAND_CACHE.get(tenant_id)
        if cached:
            return {**cached, "persistence_error": cached.get("persistence_error") or str(exc)}
        try:
            instances = _list_ec2_instance_summaries(settings.aws_region)
            doc = _fallback_agent_command_doc(
                settings=settings,
                instances=instances,
                run_id=None,
                status="degraded",
                error=str(exc),
            )
            _LATEST_COMMAND_CACHE[tenant_id] = doc
            return doc
        except Exception as fallback_exc:
            logger.exception("agent-command: live AWS latest fallback failed for %s", tenant_id)
            return {**_empty_agent_command_doc(settings), "status": "error", "persistence_error": str(fallback_exc)}

    return _empty_agent_command_doc(settings)
