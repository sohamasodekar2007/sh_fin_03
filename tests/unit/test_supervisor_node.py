from unittest.mock import Mock

from services.orchestrator.legacy.supervisor_node import (
    build_supervisor_node,
)
from packages.schemas.policy import PolicyDecision


def test_supervisor_blocks_invalid_proposal() -> None:
    adapter = Mock()
    supervisor_node = build_supervisor_node(adapter)

    original_state = {
        "proposals": [
            {
                "resource_id": "i-invalid"
            }
        ]
    }

    result = supervisor_node(original_state)

    assert result["supervisor_summary"] == {
        "total": 1,
        "auto_approved": 0,
        "human_review": 0,
        "blocked": 1,
    }

    assert (
        result["policy_decisions"][0]["outcome"]
        == "blocked"
    )

    adapter.evaluate.assert_not_called()


def test_supervisor_processes_valid_proposal() -> None:
    adapter = Mock()

    adapter.evaluate.return_value = PolicyDecision(
        proposal_id="proposal-1",
        outcome="human_review",
        reason_codes=["HUMAN_REQUIRED"],
        policy_version="test-v1",
    )

    supervisor_node = build_supervisor_node(adapter)

    state = {
        "proposals": [
            {
                "proposal_id": "proposal-1",
                "tenant_id": "tenant-test",
                "snapshot_id": "snapshot-test",
                "resource_id": "i-test123",
                "resource_type": "ec2_instance",
                "action_template": "ec2.stop.v1",
                "environment": "staging",
                "risk_level": "medium",
                "rationale": "Instance appears idle",
                "parameters": {"dry_run": True},
                "estimated_monthly_savings_usd": "5",
            }
        ]
    }

    result = supervisor_node(state)

    assert result["supervisor_summary"][
        "human_review"
    ] == 1

    assert state.get("policy_decisions") is None
