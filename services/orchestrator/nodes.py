"""
Node functions for the LangGraph pipeline (spec section 4).

    Monitor    — services.adapters (multi-cloud) -> services.focus.normalizer
                 -> UnifiedResource fleet. Degrades to each adapter's own
                 synthetic fleet when no CloudAccount is onboarded/reachable.
    Analyzer   — services.analyzer.service.analyze(): deterministic rules
                 (services.analyzer.rules) + sklearn IsolationForest
                 (services.analyzer.isolation_forest).
    Decision   — services.decision.service.decide(): deterministic proposal
                 templates, optionally reasoned over by an LLM via
                 services.decision.llm (OpenAI Structured Outputs).
    Supervisor — services.policy.policy_adapter.PolicyAdapter: the
                 deterministic risk-scoring gatekeeper. The LLM never
                 reaches this node's decision.
    Executor   — services.executor.simulated_executor.SimulatedExecutor:
                 idempotent, audited, template-mapped — never a free-form
                 command, never a live call while EXECUTION_ENABLED=false.
    Verifier   — services.verifier.health: ROI ledger entry per execution.

Explainability (spec's Generative UI / Agent Activity feed): every node
calls _trace_event() before returning; the WebSocket feed
(apps/api/ws/agent_feed.py) and the REST /v1/agent-activity endpoint are
both driven by these entries, not by separate hand-maintained state.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from uuid import uuid4

from apps.api.config import get_settings
from packages.schemas.policy import ActionProposal
from packages.schemas.unified_resource import UnifiedResource
from services.executor.execution_audit import InMemoryExecutionAuditRepository
from services.executor.simulated_executor import SimulatedExecutor
from services.policy.policy_adapter import PolicyAdapter

logger = logging.getLogger(__name__)

# Module-level singletons: the audit repository is the idempotency ledger
# and must survive across runs within this process. Swap
# InMemoryExecutionAuditRepository for a Mongo-backed implementation of the
# same ExecutionAuditRepository Protocol to persist it across restarts.
_audit_repository = InMemoryExecutionAuditRepository()
_executor = SimulatedExecutor(audit_repository=_audit_repository, execution_enabled=get_settings().execution_enabled)
_policy_adapter = PolicyAdapter(execution_enabled=get_settings().execution_enabled)


def _trace_event(agent: str, summary: dict) -> dict:
    """Partial state update with one new trace entry. graph.py declares
    `trace` with an operator.add reducer, so LangGraph appends this to the
    accumulated trace rather than replacing it."""
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
# Node 1 — monitor
# ---------------------------------------------------------------------------

def monitor(state: dict) -> dict:
    """Collect this tenant's connected CloudAccounts across every provider
    via services.adapters, normalizing everything to UnifiedResource. Falls
    back to one demo CloudAccount per provider (aws/gcp/azure/onprem) when
    the tenant hasn't onboarded a real account yet, so the pipeline always
    has real, multi-cloud data to run against."""
    from services.adapters.base import get_adapter
    from services.focus.sample_data import daily_cost_series

    run_id = state.get("run_id", "unknown")
    tenant_id = state.get("tenant_id", "demo-tenant")
    accounts: list = state.get("cloud_accounts", [])

    if not accounts:
        from packages.schemas.schemas import CloudAccount

        accounts = [
            CloudAccount(tenant_id=tenant_id, provider="aws", display_name="Demo AWS", account_id="123456789012", region="us-east-1"),
            CloudAccount(tenant_id=tenant_id, provider="gcp", display_name="Demo GCP", account_id="cloudcare-demo-project", region="us-central1"),
            CloudAccount(tenant_id=tenant_id, provider="azure", display_name="Demo Azure", account_id="cloudcare-demo-subscription", region="eastus"),
            CloudAccount(tenant_id=tenant_id, provider="onprem", display_name="Demo Datacenter", account_id="dc-pune-01", region="dc-pune-01"),
        ]

    resources: list[UnifiedResource] = []
    providers_used: dict[str, int] = {}
    for account in accounts:
        try:
            adapter = get_adapter(account.provider)
            import asyncio

            collected = asyncio.run(adapter.collect(account))
            resources.extend(collected)
            providers_used[account.provider] = providers_used.get(account.provider, 0) + len(collected)
        except Exception as exc:  # noqa: BLE001
            logger.warning("monitor: adapter for provider=%s failed (%s) — skipping this account.", account.provider, exc)

    daily_costs = daily_cost_series(base=sum(r.effective_cost for r in resources) or 320.0)

    observation = {
        "run_id": run_id,
        "snapshot_id": str(uuid4()),
        "resources": [r.model_dump(mode="json") for r in resources],
        "resources_scanned": len(resources),
        "providers": providers_used,
        "daily_costs": daily_costs,
    }

    return {
        "observation": observation,
        "status": "analyzing",
        **_trace_event("Monitor", {"resources_scanned": len(resources), "providers": providers_used}),
    }


# ---------------------------------------------------------------------------
# Node 2 — analyze
# ---------------------------------------------------------------------------

def analyze(state: dict) -> dict:
    from services.analyzer.service import analyze as run_analyzer

    observation = state.get("observation", {})
    resources = [UnifiedResource.model_validate(r) for r in observation.get("resources", [])]
    daily_costs = observation.get("daily_costs", [])

    findings = run_analyzer(resources, daily_costs)

    return {
        "findings": findings,
        "status": "review",
        **_trace_event(
            "Analyzer",
            {
                "resources_evaluated": len(resources),
                "findings": len(findings),
                "rule_ids": sorted({f["rule_id"] for f in findings}),
            },
        ),
    }


# ---------------------------------------------------------------------------
# Node 3 — decide
# ---------------------------------------------------------------------------

def decide(state: dict) -> dict:
    from services.decision.service import decide as run_decision

    observation = state.get("observation", {})
    findings = state.get("findings", [])
    tenant_id = state.get("tenant_id", "demo-tenant")

    proposals = run_decision(observation, findings, tenant_id)
    return {"proposals": proposals, **_trace_event("Decision", {"proposals": len(proposals)})}


# ---------------------------------------------------------------------------
# Node 4 — supervise
# ---------------------------------------------------------------------------

def supervise(state: dict) -> dict:
    raw_proposals = state.get("proposals", [])
    approvals: list[dict] = []
    outcomes = {"auto_approved": 0, "human_review": 0, "blocked": 0}

    for raw in raw_proposals:
        try:
            proposal = ActionProposal.model_validate(raw)
        except Exception as exc:  # noqa: BLE001
            logger.warning("supervise: invalid proposal skipped (%s)", exc)
            continue
        decision = _policy_adapter.evaluate(proposal)
        outcomes[decision.outcome] = outcomes.get(decision.outcome, 0) + 1
        approvals.append(decision.model_dump(mode="json"))

    # At least one auto-approved (or human-review) decision advances the
    # graph to `execute`; a run with only blocked decisions goes straight
    # to `verify` with nothing to execute (see route_after_supervisor).
    supervisor_decision = "execute" if any(a["outcome"] in ("auto_approved", "human_review") for a in approvals) else "human_review"

    return {
        "approvals": approvals,
        "supervisor_decision": supervisor_decision,
        **_trace_event("Supervisor", {"outcomes": outcomes}),
    }


# ---------------------------------------------------------------------------
# Node 5 — execute
# ---------------------------------------------------------------------------

def execute(state: dict) -> dict:
    raw_proposals = {p["proposal_id"]: p for p in state.get("proposals", [])}
    raw_decisions = state.get("approvals", [])

    execution_log: list[dict] = []
    for raw_decision in raw_decisions:
        proposal_raw = raw_proposals.get(raw_decision.get("proposal_id"))
        if proposal_raw is None:
            continue
        try:
            proposal = ActionProposal.model_validate(proposal_raw)
            from packages.schemas.policy import PolicyDecision

            decision = PolicyDecision.model_validate(raw_decision)
        except Exception as exc:  # noqa: BLE001
            logger.warning("execute: skipping invalid proposal/decision pair (%s)", exc)
            continue

        record = _executor.execute(proposal=proposal, decision=decision)
        execution_log.append(record.model_dump(mode="json"))

    return {
        "execution_log": execution_log,
        "status": "executing",
        **_trace_event("Executor", {"executed": len(execution_log), "simulated": sum(r["status"] == "simulated" for r in execution_log)}),
    }


# ---------------------------------------------------------------------------
# Node 6 — verify
# ---------------------------------------------------------------------------

def verify(state: dict) -> dict:
    from services.verifier.health import verify_action

    proposals_by_id = {p["proposal_id"]: p for p in state.get("proposals", [])}
    feedback = [
        verify_action(record, proposals_by_id.get(record["proposal_id"], {}))
        for record in state.get("execution_log", [])
    ]

    return {
        "feedback": feedback,
        "status": "verified",
        **_trace_event(
            "Verifier",
            {
                "verified": len(feedback),
                "total_realized_monthly_savings_usd": round(sum(f["realized_monthly_savings_usd"] for f in feedback), 2),
            },
        ),
    }
