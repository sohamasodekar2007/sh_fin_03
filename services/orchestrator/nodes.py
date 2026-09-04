"""
Node functions for the LangGraph pipeline (blueprint section 3.1).

Implementation status:
    ✅ monitor   — calls collector.ec2 + collector.cloudwatch;
                   degrades to mock_data.RESOURCES when collectors raise
                   NotImplementedError (AWS not yet connected).
    ✅ analyze   — runs all 5 rule functions from services.analyzer.rules
                   over every resource in observation; collects real Findings.
    🔲 decide    — stub; replace with LLM call (OpenRouter) in Days 5-7.
    🔲 supervise — stub; replace with policy.engine.evaluate() in Days 5-7.
    🔲 execute   — stub; replace with executor.actions in Days 8-10.
    🔲 verify    — stub; replace with verifier.health in Days 8-10.

Each node receives and returns a dict shaped like CloudCareState
(app/models/schemas.py) so LangGraph can merge partial updates.

Explainability (blueprint §6.3): every node MUST call _trace_event() before
returning. The frontend Agent Activity feed is driven by these entries.
"""

from __future__ import annotations

import logging
import random
from datetime import datetime, timezone

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------

def _trace_event(agent: str, summary: dict) -> dict:
    """
    Return a partial state update with a single new trace entry.

    Because graph.py declares `trace` with an operator.add reducer,
    LangGraph *appends* the returned list to the accumulated trace rather
    than replacing it — so nodes only return the new entry, not the full list.
    """
    return {
        "trace": [
            {
                "agent": agent,
                "at": datetime.now(timezone.utc).isoformat(),
                "summary": summary,
            }
        ]
    }


# ---------------------------------------------------------------------------
# Mock metric generator
# ---------------------------------------------------------------------------

def _mock_metrics_for(resource: dict) -> tuple[list[dict], list[dict]]:
    """
    Generate 14 days of synthetic CloudWatch-shaped metric samples for a
    resource dict.  Used as the degraded path when the real collector is
    not yet connected.

    Returns:
        cpu_samples:     list of {"Timestamp": str, "Average": float}
        network_samples: list of {"Timestamp": str, "Sum": float}
    """
    random.seed(resource["id"])          # reproducible per instance
    cpu_base = resource.get("cpu_p95", 20.0)
    cpu_samples = [
        {"Timestamp": f"day-{i}", "Average": max(0.0, cpu_base + random.gauss(0, 2))}
        for i in range(14)
    ]
    # Low network for idle instances, moderate for others.
    net_base = 2_000_000.0 if cpu_base < 10 else 50_000_000.0
    network_samples = [
        {"Timestamp": f"day-{i}", "Sum": max(0.0, net_base + random.gauss(0, net_base * 0.1))}
        for i in range(14)
    ]
    return cpu_samples, network_samples


# ---------------------------------------------------------------------------
# Node 1 — monitor
# ---------------------------------------------------------------------------

def monitor(state: dict) -> dict:
    """
    Collect EC2 inventory + CloudWatch metrics.

    Real path  : calls collector.ec2.list_instances() and
                 collector.cloudwatch.get_cpu_utilization().
    Degraded path: when either collector raises NotImplementedError (AWS
                 not yet wired), falls back to mock_data.RESOURCES with a
                 clear WARNING log so the pipeline never crashes.

    Builds the `observation` dict that the rest of the graph depends on:
        {
            "resources": [
                {
                    "id": str,
                    "cpu_p95": float,
                    "monthly_cost_usd": float,
                    "tags": dict,
                    "environment": str,
                    "cpu_samples": [{"Timestamp": str, "Average": float}, ...],
                    "network_samples": [{"Timestamp": str, "Sum": float}, ...],
                },
                ...
            ],
            "resources_scanned": int,
            "source": "aws" | "mock",
        }
    """
    run_id = state.get("run_id", "unknown")
    region = state.get("account_id", "ap-south-1")   # account_id doubles as region hint
    source = "aws"
    raw_resources: list[dict] = []

    # ------------------------------------------------------------------ #
    # 1. Try real AWS collectors                                           #
    # ------------------------------------------------------------------ #
    try:
        from packages.aws.aws_session import assumed_session
        from services.collector.cloudwatch import get_cpu_utilization
        from services.collector.ec2 import list_instances

        session = assumed_session(run_id)
        instances = list_instances(session, region)

        for inst in instances:
            instance_id = inst.get("InstanceId", "unknown")
            tags_raw = inst.get("Tags", [])
            tags = {t["Key"]: t["Value"] for t in tags_raw}
            environment = tags.get("env", tags.get("Environment", "prod"))

            # CloudWatch: 14-day CPU window
            cpu_data = get_cpu_utilization(session, instance_id, region, days=14)
            cpu_values = [p["Average"] for p in cpu_data if "Average" in p]

            # Network: not yet in the collector interface — will be added
            # when collector.cloudwatch grows get_network_utilization().
            network_data: list[dict] = []

            raw_resources.append(
                {
                    "id": instance_id,
                    "cpu_p95": _percentile(cpu_values, 95) if cpu_values else 0.0,
                    "monthly_cost_usd": 0.0,   # enriched by cost_explorer later
                    "tags": tags,
                    "environment": environment,
                    "cpu_samples": cpu_data,
                    "network_samples": network_data,
                }
            )

        logger.info("monitor: collected %d instances from AWS (run_id=%s)", len(raw_resources), run_id)

    except NotImplementedError:
        logger.warning(
            "monitor: collector raised NotImplementedError — AWS not yet "
            "connected. Degrading to mock_data.RESOURCES for run_id=%s.",
            run_id,
        )
        source = "mock"
        raw_resources = _build_mock_resources()

    except Exception as exc:  # noqa: BLE001
        logger.warning(
            "monitor: unexpected collector error (%s) — degrading to mock data for run_id=%s.",
            exc,
            run_id,
        )
        source = "mock"
        raw_resources = _build_mock_resources()

    observation = {
        "resources": raw_resources,
        "resources_scanned": len(raw_resources),
        "source": source,
    }

    return {
        "observation": observation,
        "status": "analyzing",
        **_trace_event(
            "Monitor",
            {
                "resources_scanned": len(raw_resources),
                "source": source,
            },
        ),
    }


def _build_mock_resources() -> list[dict]:
    """Convert mock_data.RESOURCES into the observation resource shape."""
    from apps.api.mock_data import RESOURCES

    result = []
    for r in RESOURCES:
        cpu_samples, network_samples = _mock_metrics_for(r.model_dump())
        result.append(
            {
                "id": r.id,
                "cpu_p95": r.cpu_p95,
                "monthly_cost_usd": r.monthly_cost_usd,
                "tags": r.tags,
                "environment": r.environment,
                "cpu_samples": cpu_samples,
                "network_samples": network_samples,
            }
        )
    return result


def _percentile(values: list[float], pct: float) -> float:
    """Local percentile helper (mirrors the one in rules.py, kept here to
    avoid a circular import between nodes and the analyzer)."""
    if not values:
        return 0.0
    values = sorted(values)
    k = (len(values) - 1) * (pct / 100)
    f, c = int(k), min(int(k) + 1, len(values) - 1)
    if f == c:
        return values[f]
    return values[f] + (values[c] - values[f]) * (k - f)


# ---------------------------------------------------------------------------
# Node 2 — analyze
# ---------------------------------------------------------------------------

def analyze(state: dict) -> dict:
    """
    Run all 5 rule functions from services.analyzer.rules over every
    resource in observation["resources"], collecting real Finding objects.

    Rules applied per resource:
        1. classify_idle             — CPU/network p95 over 7-day window
        2. classify_over_provisioned — CPU p95 over 14-day window
        3. classify_unattached_ebs   — EBS volumes not attached (skipped if
                                       resource has no ebs_volumes key)
        4. classify_nonprod_schedule — off-hours CPU for non-prod envs
        5. classify_spend_anomaly    — z-score vs 14-day trailing mean
                                       (needs daily_costs in observation)

    Each Finding is serialised to a plain dict before being stored in state
    so LangGraph can merge it without Pydantic dependency issues.
    """
    from services.analyzer.rules import (
        EBSVolume,
        MetricSample,
        classify_idle,
        classify_nonprod_schedule,
        classify_over_provisioned,
        classify_spend_anomaly,
        classify_unattached_ebs,
    )

    observation = state.get("observation", {})
    resources: list[dict] = observation.get("resources", [])
    findings: list[dict] = []

    for resource in resources:
        resource_id = resource.get("id", "unknown")
        tags = resource.get("tags", {})
        environment = resource.get("environment", "prod")

        # Build MetricSample list from raw cpu/network samples.
        cpu_samples = resource.get("cpu_samples", [])
        network_samples = resource.get("network_samples", [])

        # Align cpu + network by index (both lists are same length from monitor).
        metric_samples: list[MetricSample] = []
        for i, cpu_pt in enumerate(cpu_samples):
            cpu_val = cpu_pt.get("Average", 0.0)
            net_val = network_samples[i]["Sum"] if i < len(network_samples) else 0.0
            # Derive hour from Timestamp if available, default to midday.
            ts = cpu_pt.get("Timestamp", "")
            try:
                hour = datetime.fromisoformat(ts).hour
            except (ValueError, TypeError):
                hour = 12
            metric_samples.append(MetricSample(cpu=cpu_val, network_bytes=net_val, hour=hour))

        # ---- Rule 1: idle ------------------------------------------------
        finding = classify_idle(metric_samples, tags)
        if finding:
            findings.append({**finding.__dict__, "resource_id": resource_id})
            logger.debug("analyze: %s flagged by %s", resource_id, finding.rule_id)

        # ---- Rule 2: over-provisioned ------------------------------------
        finding = classify_over_provisioned(metric_samples, tags)
        if finding:
            findings.append({**finding.__dict__, "resource_id": resource_id})
            logger.debug("analyze: %s flagged by %s", resource_id, finding.rule_id)

        # ---- Rule 3: unattached EBS --------------------------------------
        for vol in resource.get("ebs_volumes", []):
            ebs = EBSVolume(volume_id=vol.get("VolumeId", ""), state=vol.get("State", ""))
            finding = classify_unattached_ebs(ebs, tags)
            if finding:
                findings.append({**finding.__dict__, "resource_id": resource_id})
                logger.debug("analyze: EBS %s flagged by %s", vol.get("VolumeId"), finding.rule_id)

        # ---- Rule 4: non-prod schedule -----------------------------------
        finding = classify_nonprod_schedule(metric_samples, tags, environment)
        if finding:
            findings.append({**finding.__dict__, "resource_id": resource_id})
            logger.debug("analyze: %s flagged by %s", resource_id, finding.rule_id)

    # ---- Rule 5: spend anomaly (operates on the full cost series) --------
    daily_costs: list[float] = observation.get("daily_costs", [])
    finding = classify_spend_anomaly(daily_costs)
    if finding:
        findings.append({**finding.__dict__, "resource_id": "account-level"})
        logger.debug("analyze: spend anomaly flagged — z_score=%s", finding.evidence.get("z_score"))

    logger.info(
        "analyze: %d finding(s) from %d resource(s) (source=%s)",
        len(findings),
        len(resources),
        observation.get("source", "unknown"),
    )

    return {
        "findings": findings,
        "status": "review",
        **_trace_event(
            "Analyzer",
            {
                "resources_evaluated": len(resources),
                "findings": len(findings),
                "rule_ids": list({f["rule_id"] for f in findings}),
            },
        ),
    }


# ---------------------------------------------------------------------------
# Nodes 3-6 — stubs (unchanged, pending Days 5-10 tracks)
# ---------------------------------------------------------------------------

def decide(state: dict) -> dict:
    """
    Turn this run's Analyzer findings into schema-valid ActionProposals.

    Deterministic (services.decision.service.build_proposals) — no LLM call
    required to run or test this node. An LLM may later be added purely to
    generate the human-readable `rationale` string; it must never decide
    action_type, risk_level, or expected_monthly_savings.
    """
    from services.decision.service import build_proposals

    observation = state.get("observation", {})
    findings = state.get("findings", [])
    proposals = build_proposals(observation, findings)
    return {"proposals": proposals, **_trace_event("Decision", {"proposals": len(proposals)})}

def supervise(state: dict) -> dict:
    # TODO: call app.services.policy.engine.evaluate() using the real policy
    # matrix (blueprint 6.1) — this stub always approves low-risk proposals.
    approvals = [{"decision": "execute", "reason": "low risk, dev environment"}]
    return {
        "approvals": approvals,
        "supervisor_decision": "execute",
        **_trace_event("Supervisor", {"decision": "execute"}),
    }


def execute(state: dict) -> dict:
    # TODO: call app.services.executor.actions with an idempotency key —
    # see blueprint 10.2 for the reference implementation.
    execution_log = [{"template_id": "ec2.stop.v1", "result": "stopped", "rollback_template": "ec2.start.v1"}]
    return {"execution_log": execution_log, "status": "executing", **_trace_event("Executor", {"executed": 1})}


def supervise(state: dict) -> dict:
    """Evaluate proposals and stop at human review."""
    from services.policy import engine as policy_engine

    proposals = state.get("proposals", [])
    reviews: list[dict] = []
    for proposal in proposals:
        tags = proposal.get("tags") or {}
        result = policy_engine.evaluate(
            environment=proposal.get("environment", "unknown"),
            risk_level=proposal.get("risk_level", "high"),
            template_id=proposal.get("template_id", ""),
            has_owner_tag=bool(tags.get("Owner") or tags.get("owner")),
            is_protected=str(tags.get("Protected", tags.get("protected", ""))).lower() == "true",
        )
        reviews.append(
            {
                "proposal_id": proposal.get("proposal_id"),
                "decision": "blocked" if not result.approved else "human_review",
                "auto_execute": False,
                "requires_human_approval": result.approved,
                "reason": result.reason,
            }
        )

    blocked = sum(1 for review in reviews if review["decision"] == "blocked")
    pending = len(reviews) - blocked
    return {
        "approvals": reviews,
        "supervisor_decision": "human_review",
        "status": "review",
        **_trace_event("Supervisor", {"pending_human_review": pending, "blocked": blocked}),
    }


def execute(state: dict) -> dict:
    """Do not fake AWS execution from the in-memory graph."""
    approved = [p for p in state.get("proposals", []) if p.get("status") == "approved"]
    execution_log = [
        {
            "proposal_id": p.get("proposal_id"),
            "action_type": p.get("action_type"),
            "result": "awaiting_http_executor_dispatch",
            "actual_aws_call_made": False,
        }
        for p in approved
    ]
    return {
        "execution_log": execution_log,
        "status": "executing" if execution_log else "review",
        **_trace_event("Executor", {"queued": len(execution_log), "actual_aws_calls": 0}),
    }


def verify(state: dict) -> dict:
    # TODO: call app.services.verifier.health / savings — see blueprint 10.3.
    feedback = [{"status": "verified", "realized_savings": 14.20}]
    return {"feedback": feedback, "status": "verified", **_trace_event("Verifier", {"status": "verified"})}
