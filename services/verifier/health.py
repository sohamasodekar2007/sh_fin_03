"""
Verifier Agent — the 6th node in the LangGraph pipeline, closing the loop
the spec's Executor Agent asks for: "Generates exact ROI metrics pre- and
post-execution to update the primary ledger."

SimulatedExecutor never makes a live API call (by design — see
services/executor/simulated_executor.py), so there's no real post-action
CloudWatch window to sample yet. This computes the ROI ledger entry from
the ExecutionRecord itself: whether the action was actually simulated (not
blocked/disabled by the Supervisor or the executor's own safety checks),
and the proposal's estimated monthly savings, annualized into the feedback
record the `verify` node appends to CloudCareState.feedback.

A live deployment extends this to pull a short post-action CloudWatch
window and compare it against the pre-action baseline, triggering the
action_template's rollback_template (services/executor/registry.py) if
regression_detected — the ROI math and feedback shape don't change either way.
"""

from __future__ import annotations

from typing import Any


def verify_action(execution_record: dict[str, Any], proposal: dict[str, Any]) -> dict[str, Any]:
    status = execution_record.get("status")
    realized = status == "simulated"
    monthly_savings = float(proposal.get("estimated_monthly_savings_usd", 0))

    return {
        "proposal_id": execution_record.get("proposal_id"),
        "resource_id": execution_record.get("resource_id"),
        "status": "verified" if realized else "not_realized",
        "execution_status": status,
        "realized_monthly_savings_usd": round(monthly_savings, 2) if realized else 0.0,
        "realized_annual_savings_usd": round(monthly_savings * 12, 2) if realized else 0.0,
        "regression_detected": False,
    }
