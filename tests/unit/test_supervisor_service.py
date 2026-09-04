from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import services.supervisor.service as supervisor_service


def _proposal(pid: str, template_id: str, risk_level: str, environment: str, instance_id: str) -> dict:
    return {
        "proposal_id": pid,
        "resource_arn": f"arn:aws:ec2:ap-south-1:demo:instance/{instance_id}",
        "action_type": "stop_instance",
        "template_id": template_id,
        "parameters": {"instance_id": instance_id, "region": "ap-south-1"},
        "expected_monthly_savings": "42.00",
        "risk_level": risk_level,
        "environment": environment,
        "confidence": 0.8,
        "evidence": [{"metric": "cpu_p95", "value": 2.0, "window_days": 14}],
        "rollback_plan": {"template_id": "ec2.start.v1"} if template_id == "ec2.stop.v1" else None,
        "requires_human_approval": True,
        "status": "proposed",
        "rationale": f"{template_id} detected on {instance_id}",
    }


def _mock_db(obs_doc: dict | None = None):
    mock_db = MagicMock()

    cloud_snapshots = MagicMock()
    cloud_snapshots.find_one = AsyncMock(return_value=obs_doc if obs_doc is not None else {"resources": []})

    users = MagicMock()
    users.find_one = AsyncMock(return_value=None)  # no email on file -> approval email silently skipped

    resource_metrics = MagicMock()
    resource_metrics.find_one = AsyncMock(return_value=None)  # no metrics window -> confidence uses finding-only

    proposals = MagicMock()
    proposals.update_one = AsyncMock()

    supervisor_reviews = MagicMock()
    supervisor_reviews.insert_many = AsyncMock()

    mock_db.cloud_snapshots = cloud_snapshots
    mock_db.users = users
    mock_db.proposals = proposals
    mock_db.supervisor_reviews = supervisor_reviews

    collections = {
        "cloud_snapshots": cloud_snapshots,
        "users": users,
        "resource_metrics": resource_metrics,
        "proposals": proposals,
        "supervisor_reviews": supervisor_reviews,
    }
    mock_db.__getitem__.side_effect = lambda name: collections.get(name, MagicMock())

    return mock_db, proposals


# ---------------------------------------------------------------------------
# Supervisor step: never auto-approves, regardless of policy engine outcome
# ---------------------------------------------------------------------------


@patch("services.supervisor.service.log_agent_run", new_callable=AsyncMock)
def test_supervisor_step_never_produces_approved_status(mock_log_agent_run):
    mock_db, mock_proposals = _mock_db(obs_doc={"resources": []})

    decision_result = {
        "proposals": [
            _proposal("p1", "ec2.stop.v1", "low", "development", "i-1"),
            _proposal("p2", "ec2.stop.v1", "low", "production", "i-2"),
            _proposal("p3", "unknown.template.v1", "high", "development", "i-3"),
        ]
    }

    result = asyncio.run(
        supervisor_service.run_supervisor_step(
            mock_db, "demo-tenant", "run-1", "acct-1", "ap-south-1", decision_result
        )
    )

    statuses = {r["proposal_id"]: r["status"] for r in result["reviewed"]}
    # p1 would be auto-executable by the policy engine alone (low risk, dev,
    # no owner tag -> actually requires approval; see engine.py) — the point
    # is that NOTHING ever comes out "approved" from this step.
    assert set(statuses.values()) <= {"pending_approval", "blocked"}
    assert "approved" not in statuses.values()

    # Unknown template is blocked outright.
    assert statuses["p3"] == "blocked"
    # Production always requires human approval, never auto-executes —
    # and PolicyAdapter forces this even before considering risk/owner tag.
    assert statuses["p2"] == "pending_approval"

    mock_log_agent_run.assert_awaited_once()
    log_kwargs = mock_log_agent_run.await_args.kwargs
    assert log_kwargs["agent"] == "Supervisor"
    assert log_kwargs["status"] == "success"


@patch("services.supervisor.service.log_agent_run", new_callable=AsyncMock)
def test_supervisor_step_updates_each_proposal_document(mock_log_agent_run):
    mock_db, mock_proposals = _mock_db(obs_doc={"resources": []})

    decision_result = {"proposals": [_proposal("p1", "ec2.stop.v1", "low", "development", "i-1")]}

    asyncio.run(
        supervisor_service.run_supervisor_step(
            mock_db, "demo-tenant", "run-1", "acct-1", "ap-south-1", decision_result
        )
    )

    mock_proposals.update_one.assert_awaited_once()
    filter_arg, update_arg = mock_proposals.update_one.await_args.args
    assert filter_arg == {"proposal_id": "p1"}
    assert "status" in update_arg["$set"]
    assert update_arg["$set"]["status"] in {"pending_approval", "blocked"}
