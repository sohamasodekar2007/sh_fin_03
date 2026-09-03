"""
Chat Orchestrator function-calling tools (spec section 5). Each entry maps
one OpenAI tool name straight onto a backend agent trigger — the LLM never
free-forms an action, it can only pick one of these and get back real
pipeline state.
"""

from __future__ import annotations

from typing import Any

TOOL_SCHEMAS = [
    {
        "type": "function",
        "function": {
            "name": "trigger_monitor_agent",
            "description": "Run a full scan: Monitor -> Analyzer -> Decision -> Supervisor -> Executor -> Verifier across every connected cloud account. Use this when the user asks to scan, refresh, or check their cloud spend.",
            "parameters": {"type": "object", "properties": {}, "additionalProperties": False},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "run_analyzer_agent",
            "description": "List wasted/idle/over-provisioned/anomalous resources found in the most recent scan, without triggering a new one. Use this when the user asks to see wasted resources or findings.",
            "parameters": {"type": "object", "properties": {}, "additionalProperties": False},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_savings_summary",
            "description": "Get total monthly spend, wasted spend, and realized savings from the most recent scan. Use this when the user asks about cost, spend, or savings.",
            "parameters": {"type": "object", "properties": {}, "additionalProperties": False},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "list_pending_approvals",
            "description": "List action proposals the Supervisor Agent routed to human review (REQUIRE_HUMAN) and are still awaiting an approve/reject decision. Use this when the user asks what needs their approval.",
            "parameters": {"type": "object", "properties": {}, "additionalProperties": False},
        },
    },
]


async def trigger_monitor_agent(tenant_id: str) -> dict[str, Any]:
    from apps.api.pipeline import run_pipeline

    result = await run_pipeline(tenant_id)
    return {
        "resources_scanned": result.get("observation", {}).get("resources_scanned", 0),
        "findings": len(result.get("findings", [])),
        "proposals": len(result.get("proposals", [])),
        "executed": len(result.get("execution_log", [])),
    }


def run_analyzer_agent(tenant_id: str) -> dict[str, Any]:
    from apps.api.pipeline import get_last_run

    run = get_last_run(tenant_id)
    if not run:
        return {"message": "No scan has been run yet — call trigger_monitor_agent first."}

    findings = run.get("findings", [])
    return {
        "finding_count": len(findings),
        "findings": [
            {"resource_id": f["resource_id"], "rule_id": f["rule_id"], "severity": f["severity"], "confidence": f["confidence"]}
            for f in findings[:10]
        ],
    }


def get_savings_summary(tenant_id: str) -> dict[str, Any]:
    from apps.api.pipeline import get_last_run

    run = get_last_run(tenant_id)
    if not run:
        return {"message": "No scan has been run yet — call trigger_monitor_agent first."}

    resources = run.get("observation", {}).get("resources", [])
    feedback = run.get("feedback", [])
    total_monthly_spend = round(sum(r.get("effective_cost", 0) for r in resources) * 30, 2)
    savings_this_month = round(sum(f.get("realized_monthly_savings_usd", 0) for f in feedback), 2)
    return {
        "total_monthly_spend_usd": total_monthly_spend,
        "savings_this_month_usd": savings_this_month,
        "resources_monitored": len(resources),
    }


def list_pending_approvals(tenant_id: str) -> dict[str, Any]:
    from apps.api.pipeline import get_last_run

    run = get_last_run(tenant_id)
    if not run:
        return {"pending": []}

    decisions_by_id = {d["proposal_id"]: d for d in run.get("approvals", [])}
    pending = [
        p
        for p in run.get("proposals", [])
        if decisions_by_id.get(p["proposal_id"], {}).get("outcome") == "human_review"
    ]
    return {"pending": pending}


TOOL_IMPLEMENTATIONS = {
    "trigger_monitor_agent": trigger_monitor_agent,
    "run_analyzer_agent": run_analyzer_agent,
    "get_savings_summary": get_savings_summary,
    "list_pending_approvals": list_pending_approvals,
}
