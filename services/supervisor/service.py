"""
Supervisor agent (Phase 5) — scoring, evidence, policy outcome, and the
human-approval email/dashboard loop.

Called from two places: apps/api/routers/decision.py (the Decision agent
hands off directly, no human in the loop for the HANDOFF itself — see
Phase 4 item 4) and apps/api/routers/supervisor.py's standalone
POST /v1/agent/supervise (manual re-run / curl / demos). Either way this
is where the pipeline genuinely stops: every proposal here ends up
"pending_approval" or "blocked", NEVER "approved" — this step never
auto-executes, whatever policy_outcome says. Only a human clicking Approve
(dashboard button or the signed email link) can move a proposal past this,
via apply_approval_status() + apps/api/routers/supervisor.py calling the
executor afterward.

SCORING
-------
confidence_score (0-1): a weighted blend of three signals —
    60% the Analyzer finding's own confidence (already 0-1)
    25% metric sample count / 14 (capped at 1.0) — 14 is the same window
        the Analyzer's own rules require before they'll fire at all
        (services/analyzer/rules.py's `len(metrics) >= 7/14` gate), so a
        proposal built on a full window scores full marks here
    15% data recency — 1.0 if the resource_metrics window closed within
        24h, decaying linearly to 0.0 at 7 days old
See _confidence_score().

risk_score (0-1): a weighted blend of four signals —
    40% environment (production=1.0, staging=0.5, development=0.2)
    25% blast radius, taken from Decision's own risk_level classification
        (low/medium/high/critical -> 0.2/0.5/0.8/1.0)
    20% reversibility — 0.0 if this build has a real rollback path for the
        action_type (only stop_instance does, via ec2.start.v1), else 1.0
    15% whether THIS proposal actually carries a rollback_plan (belt and
        suspenders on top of the action-type check above)
See _risk_score().

POLICY OUTCOME
--------------
auto_approved | needs_approval | blocked, computed by wrapping the
existing services/policy/engine.py through services/policy/policy_adapter.py
and services/orchestrator/legacy/supervisor_node.py's build_supervisor_node
— real, tested code that existed before this phase but was never wired to
a route. PolicyAdapter's own ALLOWED_ACTION_TEMPLATES is stricter than the
engine's (ec2.stop.v1 only, matching SimulatedExecutor's SUPPORTED_TEMPLATES),
so resize/schedule proposals correctly come back "blocked" — nothing in
this build can execute them, so leaving them "pending" forever would be
dishonest. Production NEVER comes back "auto_approved" — PolicyAdapter
forces "needs_approval" (human_review) for environment=="production"
unconditionally, ahead of every other check. This is informational only:
it explains WHY a proposal is pending/blocked, it never skips the human
click (see module docstring above).
"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone
from decimal import Decimal
from typing import TYPE_CHECKING, Any, Literal

from motor.motor_asyncio import AsyncIOMotorDatabase

from apps.api.config import get_settings
from packages.schemas.policy import ActionProposal as PolicyActionProposal
from services.agent_log import log_agent_run
from services.focus.metrics import ResourceMetric, get_resource_metric
from services.notifications.email import send_approval_email_sync
from services.orchestrator.legacy.supervisor_node import build_supervisor_node
from services.governance.tags import exceeds_max_risk
from services.policy import engine as policy_engine
from services.policy.policy_adapter import PolicyAdapter
from services.supervisor.approval_tokens import issue_approval_token

if TYPE_CHECKING:
    from fastapi import BackgroundTasks

logger = logging.getLogger(__name__)

ApprovalAction = Literal["approve", "reject"]

_ENV_SHORT_TO_LONG = {
    "dev": "development", "development": "development",
    "stage": "staging", "stg": "staging", "staging": "staging",
    "prod": "production", "production": "production",
}
_ENV_LONG_TO_SHORT = {"development": "dev", "staging": "staging", "production": "prod"}

_OUTCOME_DISPLAY = {"auto_approved": "auto_approved", "human_review": "needs_approval", "blocked": "blocked"}

_ENV_RISK_WEIGHT = {"production": 1.0, "staging": 0.5, "development": 0.2, "unknown": 0.7}
_RISK_LEVEL_WEIGHT = {"low": 0.2, "medium": 0.5, "high": 0.8, "critical": 1.0}
# Only stop_instance has a real rollback template in this build
# (build_proposals() only attaches rollback_plan to stop_instance — see
# services/decision/service.py). Kept as its own named factor (rather than
# folded into the rollback_plan check below) because a future action_type
# could be reversible in principle without this build having wired up its
# rollback template yet.
_REVERSIBLE_ACTION_TYPES = {"stop_instance"}

_ACTION_PLAIN_ENGLISH = {
    "stop_instance": "Stop this instance",
    "resize_instance": "Resize this instance to a smaller type",
    "schedule_instance": "Add an on/off schedule to this instance",
    "delete_volume": "Delete this detached EBS volume after taking a snapshot",
    "adjust_asg_capacity": "Reduce this Auto Scaling Group's desired capacity by one instance",
    "no_action": "No action recommended — considered and declined, see rationale",
}

_EVIDENCE_UNITS_AND_COLUMNS: dict[str, tuple[str, str]] = {
    "cpu_p95": ("percent", "x_cpu_p95"),
    "cpu_avg": ("percent", "x_cpu_avg"),
    "network_p95_bytes": ("bytes", "x_network_p95_bytes"),
    "memory_used_p95": ("percent", "x_mem_p95"),
    "memory_headroom_pct": ("percent", "x_mem_p95"),
    "off_hours_cpu_p95": ("percent", "x_cpu_p95"),
    "window_samples": ("count", "x_sample_count"),
    "current_day_usd": ("usd", "BilledCost"),
    "baseline_mean_usd": ("usd", "BilledCost"),
    "baseline_std_usd": ("usd", "BilledCost"),
    "unattached_hours": ("hours", "x_resource_state"),
}
_DEFAULT_EVIDENCE_UNIT_AND_COLUMN = ("value", "BilledCost")


# ---------------------------------------------------------------------------
# Pure scoring — no I/O, directly unit-testable
# ---------------------------------------------------------------------------


def _confidence_score(finding_confidence: float, resource_metric: ResourceMetric | None, now: datetime) -> float:
    sample_score = 0.0
    recency_score = 0.0
    if resource_metric is not None and resource_metric.sample_count:
        sample_score = min(resource_metric.sample_count / 14.0, 1.0)
        window_end = resource_metric.window_end
        if window_end.tzinfo is None:
            window_end = window_end.replace(tzinfo=timezone.utc)
        age_hours = max((now - window_end).total_seconds() / 3600.0, 0.0)
        recency_score = 1.0 if age_hours <= 24.0 else max(1.0 - (age_hours - 24.0) / (168.0 - 24.0), 0.0)

    blended = 0.6 * finding_confidence + 0.25 * sample_score + 0.15 * recency_score
    return round(min(max(blended, 0.0), 1.0), 4)


def _risk_score(environment_long: str, risk_level: str, action_type: str, rollback_plan: dict[str, Any] | None) -> float:
    env_component = _ENV_RISK_WEIGHT.get(environment_long, 0.7)
    blast_component = _RISK_LEVEL_WEIGHT.get(risk_level, 0.8)
    reversibility_component = 0.0 if action_type in _REVERSIBLE_ACTION_TYPES else 1.0
    rollback_component = 0.0 if rollback_plan else 1.0

    blended = 0.4 * env_component + 0.25 * blast_component + 0.20 * reversibility_component + 0.15 * rollback_component
    return round(min(max(blended, 0.0), 1.0), 4)


def _resource_monthly_cost(resource: dict[str, Any] | None) -> Decimal:
    if not resource:
        return Decimal("300.00")
    daily = resource.get("daily_cost_usd")
    if daily is not None:
        return (Decimal(str(daily)) * 30).quantize(Decimal("0.01"))
    return Decimal(str(resource.get("monthly_cost_usd", 300.0))).quantize(Decimal("0.01"))


def _cost_breakdown(resource: dict[str, Any] | None, proposal: dict[str, Any]) -> dict[str, str]:
    """All-Decimal arithmetic end to end — the proposal's
    expected_monthly_savings is already an exact Decimal string from
    build_proposals(); this never round-trips it through float."""
    cost_current = _resource_monthly_cost(resource)
    savings_monthly = Decimal(str(proposal["expected_monthly_savings"])).quantize(Decimal("0.01"))
    cost_optimized = cost_current - savings_monthly
    if cost_optimized < Decimal("0"):
        cost_optimized = Decimal("0.00")
    savings_annual = (savings_monthly * 12).quantize(Decimal("0.01"))
    return {
        "cost_current_monthly": str(cost_current),
        "cost_optimized_monthly": str(cost_optimized.quantize(Decimal("0.01"))),
        "savings_monthly": str(savings_monthly),
        "savings_annual": str(savings_annual),
    }


def _build_evidence(proposal: dict[str, Any]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for item in proposal.get("evidence", []):
        metric = item.get("metric", "")
        unit, column = _EVIDENCE_UNITS_AND_COLUMNS.get(metric, _DEFAULT_EVIDENCE_UNIT_AND_COLUMN)
        out.append(
            {
                "metric": metric,
                "value": item.get("value"),
                "unit": unit,
                "window_days": item.get("window_days", 14),
                "source_focus_column": column,
            }
        )
    return out


def score_proposal(
    proposal: dict[str, Any],
    resource: dict[str, Any] | None,
    resource_metric: ResourceMetric | None,
    environment_long: str,
    now: datetime | None = None,
) -> dict[str, Any]:
    """Pure scoring for one proposal — confidence_score, risk_score, the
    cost breakdown, and evidence. Never touches the database or the policy
    engine (see evaluate_policy_outcome for that)."""
    now = now or datetime.now(timezone.utc)
    return {
        "confidence_score": _confidence_score(proposal.get("confidence", 0.5), resource_metric, now),
        "risk_score": _risk_score(
            environment_long, proposal["risk_level"], proposal["action_type"], proposal.get("rollback_plan")
        ),
        "evidence": _build_evidence(proposal),
        **_cost_breakdown(resource, proposal),
    }


def evaluate_policy_outcome(
    proposal: dict[str, Any],
    tenant_id: str,
    environment_long: str,
    has_owner_tag: bool,
    is_protected: bool,
) -> tuple[str, list[str]]:
    """(policy_outcome, reason_codes) — auto_approved | needs_approval |
    blocked. See module docstring: informational only, never a bypass of
    the human-approval loop."""
    env_short = _ENV_LONG_TO_SHORT.get(environment_long, "unknown")

    def evaluate_fn(proposal_dict: dict[str, Any]) -> dict[str, Any]:
        result = policy_engine.evaluate(
            environment=env_short,
            risk_level=proposal_dict["risk_level"],
            template_id=proposal_dict["action_template"],
            has_owner_tag=has_owner_tag,
            is_protected=is_protected,
        )
        return {
            "allowed": result.approved,
            "requires_human_review": result.requires_human_approval,
            "reason_codes": [result.reason],
            "policy_version": "engine-v1",
        }

    adapter = PolicyAdapter(evaluator=evaluate_fn, execution_enabled=True, execution_mode="simulation")
    node = build_supervisor_node(adapter)

    policy_proposal = PolicyActionProposal(
        proposal_id=proposal["proposal_id"],
        tenant_id=tenant_id,
        snapshot_id=proposal.get("resource_arn", "unknown"),
        resource_id=(proposal.get("parameters") or {}).get("instance_id")
        or (proposal.get("parameters") or {}).get("volume_id", "unknown"),
        resource_type="ebs_volume" if proposal["action_type"] == "delete_volume" else "ec2_instance",
        action_template=proposal["template_id"],
        environment=environment_long if environment_long in ("development", "staging", "production") else "unknown",
        risk_level=proposal["risk_level"] if proposal["risk_level"] in ("low", "medium", "high") else "high",
        provider=proposal.get("provider", "aws"),
        rationale=proposal.get("rationale", ""),
        parameters=proposal.get("parameters", {}),
        estimated_monthly_savings_usd=Decimal(str(proposal["expected_monthly_savings"])),
    )

    result = node({"proposals": [policy_proposal.model_dump(mode="json")]})
    decision = result["policy_decisions"][0]
    return _OUTCOME_DISPLAY.get(decision["outcome"], "blocked"), decision["reason_codes"]


def _environment_long_for(proposal: dict[str, Any], resource: dict[str, Any] | None) -> str:
    direct = proposal.get("environment")
    if direct in ("development", "staging", "production", "unknown"):
        return direct
    env_short_raw = str((resource or {}).get("environment", "dev")).lower()
    return _ENV_SHORT_TO_LONG.get(env_short_raw, "unknown")


# ---------------------------------------------------------------------------
# Email dispatch
# ---------------------------------------------------------------------------


def _dispatch_email(background_tasks: "BackgroundTasks | None", fn: Any, *args: Any) -> None:
    """Routes through FastAPI's BackgroundTasks when called from a route
    handler (so the request doesn't block on SMTP — Phase 5 item 3);
    otherwise (the scheduler's in-process pipeline, or a plain script) runs
    it in a thread-pool executor so it still doesn't block the event loop,
    falling back to a direct synchronous call only if no loop is running at
    all (e.g. a bare unit test)."""
    if background_tasks is not None:
        background_tasks.add_task(fn, *args)
        return
    try:
        loop = asyncio.get_running_loop()
        loop.run_in_executor(None, fn, *args)
    except RuntimeError:
        fn(*args)


async def _send_approval_email(
    db: AsyncIOMotorDatabase,
    background_tasks: "BackgroundTasks | None",
    tenant_id: str,
    proposal: dict[str, Any],
    resource: dict[str, Any] | None,
    review: dict[str, Any],
) -> None:
    settings = get_settings()
    recipient = await db.users.find_one({"tenant_id": tenant_id}, {"_id": 0, "email": 1})
    to_email = (recipient or {}).get("email")
    if not to_email:
        logger.warning("supervisor: no user email on file for tenant %s — approval email not sent", tenant_id)
        return

    proposal_id = proposal["proposal_id"]
    approve_token = issue_approval_token(proposal_id, "approve", tenant_id, settings.approval_token_secret)
    reject_token = issue_approval_token(proposal_id, "reject", tenant_id, settings.approval_token_secret)

    resource_name = (resource or {}).get("resource_name") or (resource or {}).get("name") or (
        (proposal.get("parameters") or {}).get("instance_id") or proposal.get("resource_arn", "this resource")
    )
    context = {
        "resource_name": resource_name,
        "action_plain_english": proposal.get("rationale_plain_english")
        or _ACTION_PLAIN_ENGLISH.get(proposal["action_type"], proposal["action_type"]),
        "savings_monthly": review["savings_monthly"],
        "confidence_score": review["confidence_score"],
        "risk_score": review["risk_score"],
        "rationale": proposal.get("rationale_plain_english") or proposal.get("rationale", ""),
        "approve_url": f"{settings.app_base_url}/approve/{approve_token}",
        "reject_url": f"{settings.app_base_url}/approve/{reject_token}",
    }
    _dispatch_email(background_tasks, send_approval_email_sync, to_email, context, settings)


# ---------------------------------------------------------------------------
# Orchestration
# ---------------------------------------------------------------------------


async def run_supervisor_step(
    db: AsyncIOMotorDatabase,
    tenant_id: str,
    run_id: str,
    account_id: str,
    region: str,
    decision_result: dict[str, Any],
    background_tasks: "BackgroundTasks | None" = None,
) -> dict[str, Any]:
    started_at = datetime.now(timezone.utc)
    proposals: list[dict[str, Any]] = decision_result.get("proposals", [])

    try:
        obs_doc = await db.cloud_snapshots.find_one({"account_id": account_id, "region": region}, {"_id": 0}) or {}
        resources_by_id: dict[str, dict[str, Any]] = {}
        tags_by_resource: dict[str, dict[str, Any]] = {}
        for r in obs_doc.get("resources", []):
            rid = r.get("resource_id") or r.get("instance_id")
            if rid:
                resources_by_id[rid] = r
                tags_by_resource[rid] = r.get("tags") or {}

        reviewed: list[dict[str, Any]] = []
        review_docs: list[dict[str, Any]] = []

        for p in proposals:
            params = p.get("parameters") or {}
            target_resource_id = params.get("instance_id") or params.get("volume_id", "")
            resource = resources_by_id.get(target_resource_id)
            tags = tags_by_resource.get(target_resource_id, {})
            has_owner_tag = bool(tags.get("Owner") or tags.get("owner"))
            is_protected = str(tags.get("Protected", tags.get("protected", ""))).lower() == "true"
            environment_long = _environment_long_for(p, resource)

            resource_metric = await get_resource_metric(db, tenant_id, target_resource_id) if target_resource_id else None
            score = score_proposal(p, resource, resource_metric, environment_long, now=started_at)
            policy_outcome, reason_codes = evaluate_policy_outcome(
                p, tenant_id, environment_long, has_owner_tag, is_protected
            )

            # Phase 15 — independent hard floors, re-checked here rather
            # than trusted from whatever Decision/policy_engine already
            # concluded (same "don't trust upstream" principle Phase 14
            # applied to RDS/S3). Neither of these actually changes
            # new_status below (every non-blocked outcome already lands on
            # pending_approval, never auto-executes — see this module's
            # docstring); they correct policy_outcome itself so the
            # dashboard/audit trail never displays "auto_approved" for a
            # resource with no ownership tag or a real risk_level above its
            # customer-set cloudcare:max-risk ceiling.
            missing_ownership = bool((resource or {}).get("dependency_context", {}).get("missing_ownership"))
            risk_ceiling_exceeded = exceeds_max_risk(p["risk_level"], tags)
            if policy_outcome == "auto_approved" and (missing_ownership or risk_ceiling_exceeded):
                policy_outcome = "needs_approval"
                if missing_ownership:
                    reason_codes = [*reason_codes, "MISSING_OWNERSHIP_TAG"]
                if risk_ceiling_exceeded:
                    reason_codes = [*reason_codes, "EXCEEDS_MAX_RISK_CEILING"]

            # Never auto-execute from here, whatever policy_outcome says —
            # only a human clicking Approve moves a proposal past this.
            new_status = "blocked" if policy_outcome == "blocked" else "pending_approval"

            review_doc = {
                "review_id": p["proposal_id"] + ":" + run_id,
                "tenant_id": tenant_id,
                "run_id": run_id,
                "proposal_id": p["proposal_id"],
                "resource_arn": p.get("resource_arn"),
                "policy_outcome": policy_outcome,
                "reason_codes": reason_codes,
                "created_at": started_at,
                **score,
            }
            review_docs.append(review_doc)

            update_fields: dict[str, Any] = {
                "status": new_status,
                "policy_outcome": policy_outcome,
                "confidence_score": score["confidence_score"],
                "risk_score": score["risk_score"],
                "cost_current_monthly": score["cost_current_monthly"],
                "cost_optimized_monthly": score["cost_optimized_monthly"],
                "savings_annual": score["savings_annual"],
            }
            try:
                await db.proposals.update_one({"proposal_id": p["proposal_id"]}, {"$set": update_fields})
            except Exception as err:
                logger.warning("supervisor: failed to update proposal %s: %s", p.get("proposal_id"), err)

            if new_status == "pending_approval":
                await _send_approval_email(db, background_tasks, tenant_id, p, resource, score)

            reviewed.append(
                {
                    "proposal_id": p["proposal_id"],
                    "status": new_status,
                    "policy_outcome": policy_outcome,
                    "confidence_score": score["confidence_score"],
                    "risk_score": score["risk_score"],
                    "savings_monthly": score["savings_monthly"],
                    "reason": "; ".join(reason_codes),
                }
            )

        if review_docs:
            try:
                await db.supervisor_reviews.insert_many(review_docs)
            except Exception as err:
                logger.warning("supervisor: failed to persist supervisor_reviews: %s", err)

        finished_at = datetime.now(timezone.utc)
        summary = {
            "total": len(reviewed),
            "pending_approval": sum(1 for r in reviewed if r["status"] == "pending_approval"),
            "blocked": sum(1 for r in reviewed if r["status"] == "blocked"),
        }
        payload = {
            "status": "success",
            "agent": "Supervisor",
            "run_id": run_id,
            "reviewed": reviewed,
            "summary": summary,
        }

        await log_agent_run(
            tenant_id=tenant_id,
            run_id=run_id,
            agent="Supervisor",
            status="success",
            started_at=started_at,
            finished_at=finished_at,
            input_summary={"proposals_count": len(proposals)},
            output_summary={
                "message": (
                    f"Reviewed {summary['total']} proposals — {summary['pending_approval']} pending "
                    f"human approval (email sent), {summary['blocked']} blocked. Never auto-executes."
                ),
                **summary,
            },
            payload=payload,
            error=None,
        )
        return payload

    except Exception as exc:
        finished_at = datetime.now(timezone.utc)
        try:
            await log_agent_run(
                tenant_id=tenant_id,
                run_id=run_id,
                agent="Supervisor",
                status="failed",
                started_at=started_at,
                finished_at=finished_at,
                input_summary={"proposals_count": len(proposals)},
                output_summary={"message": f"Supervisor run failed: {exc}"},
                payload={},
                error=str(exc),
            )
        except Exception:
            logger.exception("supervisor: failed to record Supervisor failure log")
        raise


async def apply_approval_status(
    db: AsyncIOMotorDatabase,
    proposal_id: str,
    tenant_id: str,
    action: ApprovalAction,
    confirmed_by: str | None,
    via: Literal["dashboard", "email"],
    reason: str | None = None,
) -> dict[str, Any]:
    """The DB-only half of approve/reject — status transition + audit
    fields. Actually enqueuing the executor on approval is the router's job
    (apps/api/routers/supervisor.py), which calls this first, then
    apps/api/routers/recommendations.py's execute_recommendation() — kept
    out of the services layer so services/ never imports apps/api/routers/."""
    now = datetime.now(timezone.utc)
    if action == "approve":
        update = {"status": "approved", "approved_at": now, "approved_by": confirmed_by, "confirmed_via": via}
    else:
        update = {
            "status": "rejected",
            "rejected_at": now,
            "rejected_by": confirmed_by,
            "confirmed_via": via,
            "rejection_reason": reason or "",
        }
    await db.proposals.update_one({"proposal_id": proposal_id, "tenant_id": tenant_id}, {"$set": update})
    return {"status": update["status"], "proposal_id": proposal_id}


async def ensure_supervisor_indexes(db: AsyncIOMotorDatabase) -> None:
    await db.supervisor_reviews.create_index([("tenant_id", 1), ("run_id", 1)], name="tenant_run")
    await db.supervisor_reviews.create_index([("proposal_id", 1)], name="proposal_id")
