"""
Decision Agent (spec section 4.3) — turns Analyzer findings into
packages.schemas.policy.ActionProposal-shaped dicts, the single canonical
proposal schema the Supervisor's PolicyAdapter and the Executor's
SimulatedExecutor both consume.

Deterministic by default: action_template, risk_level, and
estimated_monthly_savings_usd always come from build_proposals() — never
from the LLM. decide() additionally calls services.decision.llm (OpenAI,
Structured Outputs / tool calling) when OPENAI_API_KEY is set, for a second
opinion on which findings are worth acting on and a reviewer-facing
rationale; the LLM can drop a proposal but never invent risk/savings
numbers the Supervisor didn't independently compute. Matches the
blueprint's core principle: "AI may recommend and reason; deterministic
policy and templates control execution."
"""

from __future__ import annotations

from decimal import Decimal
from typing import Any
from uuid import uuid4

_RULE_TO_TEMPLATE = {
    "ec2.idle.v1": {"action_template": "ec2.stop.v1", "savings_pct": 1.0},
    "ec2.overprovisioned.v1": {"action_template": "ec2.resize.v1", "savings_pct": 0.4},
    "ec2.nonprod_schedule.v1": {"action_template": "ec2.schedule.v1", "savings_pct": 0.65},
    "ebs.unattached.v1": {"action_template": "ec2.stop.v1", "savings_pct": 1.0},
    "ml.isolation_forest.v1": {"action_template": "ec2.resize.v1", "savings_pct": 0.25},
}

_ENV_ALIAS = {
    "dev": "development", "development": "development",
    "staging": "staging",
    "prod": "production", "production": "production",
}

_RISK_BY_ENV = {
    "development": "low",
    "staging": "low",
    "production": "high",
    "unknown": "high",
}


def _resource_lookup(observation: dict[str, Any]) -> dict[str, dict[str, Any]]:
    lookup: dict[str, dict[str, Any]] = {}
    for r in observation.get("resources", []):
        rid = r.get("id") or r.get("instance_id") or r.get("resource_id")
        if rid:
            lookup[rid] = r
    return lookup


def _monthly_cost_for(resource: dict[str, Any]) -> float:
    # UnifiedResource.effective_cost is a daily figure (see
    # services/focus/normalizer.py) — daily_cost_usd/monthly_cost_usd are
    # kept for callers still on the pre-FOCUS raw AWS resource shape.
    if resource.get("effective_cost") is not None:
        return float(resource["effective_cost"]) * 30
    daily = resource.get("daily_cost_usd")
    if daily is not None:
        return float(daily) * 30
    return float(resource.get("monthly_cost_usd", 300.0))


def _environment_for(resource: dict[str, Any]) -> str:
    return _ENV_ALIAS.get(str(resource.get("environment", "unknown")).lower(), "unknown")


def _risk_level_for(environment: str) -> str:
    return _RISK_BY_ENV.get(environment, "high")


def build_proposals(observation: dict[str, Any], findings: list[dict[str, Any]], tenant_id: str = "demo-tenant") -> list[dict[str, Any]]:
    resources = _resource_lookup(observation)
    snapshot_id = observation.get("snapshot_id", observation.get("run_id", "unknown-snapshot"))
    proposals: list[dict[str, Any]] = []

    for finding in findings:
        template = _RULE_TO_TEMPLATE.get(finding["rule_id"])
        if not template:
            continue

        resource_id = finding["resource_id"]
        resource = resources.get(resource_id)
        if not resource:
            continue

        monthly_cost = _monthly_cost_for(resource)
        expected_savings = round(monthly_cost * template["savings_pct"], 2)
        environment = _environment_for(resource)
        risk_level = _risk_level_for(environment)
        region = resource.get("region", "us-east-1")
        provider = resource.get("provider", "aws")
        confidence = finding.get("confidence", 0.75)
        tags = resource.get("tags", {})
        has_owner_tag = bool(tags.get("Owner") or tags.get("owner"))
        is_protected = str(tags.get("cloudcare:exclude", tags.get("protected", ""))).lower() == "true"

        proposals.append(
            {
                "proposal_id": str(uuid4()),
                "tenant_id": tenant_id,
                "snapshot_id": snapshot_id,
                "resource_id": resource_id,
                "resource_type": resource.get("resource_type", resource.get("type", "unknown")),
                "provider": provider,
                "action_template": template["action_template"],
                "environment": environment,
                "risk_level": risk_level,
                "rationale": (
                    f"{finding['rule_id']} detected on {resource_id} "
                    f"(confidence {confidence:.2f}); estimated savings ${expected_savings}/mo."
                ),
                "parameters": {
                    "resource_id": resource_id,
                    "region": region,
                    "has_owner_tag": has_owner_tag,
                    "is_protected": is_protected,
                },
                "estimated_monthly_savings_usd": str(Decimal(str(expected_savings))),
                "confidence": confidence,
                "status": "proposed",
            }
        )

    def _priority(p: dict[str, Any]) -> float:
        risk_penalty = {"low": 0.0, "medium": 0.1, "high": 0.3}[p["risk_level"]]
        return float(p["estimated_monthly_savings_usd"]) * p["confidence"] - risk_penalty * 100

    proposals.sort(key=_priority, reverse=True)
    return proposals


_SAVINGS_DEVIATION_TOLERANCE = 0.5  # LLM's number may drift at most 50% from the deterministic estimate


def decide(observation: dict[str, Any], findings: list[dict[str, Any]], tenant_id: str = "demo-tenant") -> list[dict[str, Any]]:
    """
    Decision Agent entrypoint. Computes the deterministic proposals first —
    action_template, risk_level, and estimated_monthly_savings_usd always
    come from build_proposals(), never from the LLM. If OPENAI_API_KEY is
    set, asks the LLM (services.decision.llm.generate_action_proposals,
    constrained to a rigid tool-call schema) for a rationale and a second
    opinion on which findings are worth acting on; a resource the LLM
    didn't propose is dropped, and an LLM savings estimate that drifts more
    than 50% from the deterministic one is ignored in favor of it.

    The Supervisor Agent (services/policy/policy_adapter.py) evaluates
    whatever comes out of this function — it has no visibility into whether
    a given proposal's rationale was LLM- or template-authored, by design.
    """
    from services.decision.llm import generate_action_proposals

    deterministic = build_proposals(observation, findings, tenant_id)
    if not deterministic:
        return deterministic

    resources = _resource_lookup(observation)
    resource_context = [
        {
            "id": rid,
            "environment": r.get("environment"),
            "monthly_cost_usd": _monthly_cost_for(r),
            "tags": r.get("tags", {}),
        }
        for rid, r in resources.items()
    ]
    llm_proposals = generate_action_proposals(findings, resource_context)
    if not llm_proposals:
        return deterministic

    by_resource = {p["resource_id"]: p for p in deterministic}
    llm_by_resource = {p.get("target_resource_id"): p for p in llm_proposals}

    merged: list[dict[str, Any]] = []
    for resource_id, proposal in by_resource.items():
        llm_take = llm_by_resource.get(resource_id)
        if not llm_take:
            continue  # the LLM chose not to act on this finding — respect that as a second opinion

        deterministic_savings = float(proposal["estimated_monthly_savings_usd"])
        llm_savings = float(llm_take.get("estimated_monthly_savings", deterministic_savings))
        deviation = abs(llm_savings - deterministic_savings) / max(deterministic_savings, 1.0)
        final_savings = llm_savings if deviation <= _SAVINGS_DEVIATION_TOLERANCE else deterministic_savings

        merged.append(
            {
                **proposal,
                "estimated_monthly_savings_usd": str(Decimal(str(round(final_savings, 2)))),
                "rationale": llm_take.get("rationale", proposal["rationale"]),
            }
        )

    return merged or deterministic
