from services.orchestrator.legacy.executor_node import (
    build_executor_node,
)
from services.executor.execution_audit import (
    InMemoryExecutionAuditRepository,
)
from packages.schemas.policy import ActionProposal, PolicyDecision
from services.executor.simulated_executor import (
    SimulatedExecutor,
)


def make_proposal() -> ActionProposal:
    return ActionProposal(
        proposal_id="proposal-node-001",
        tenant_id="tenant-test",
        snapshot_id="snapshot-test",
        resource_id="i-test123",
        resource_type="ec2_instance",
        action_template="ec2.stop.v1",
        environment="development",
        risk_level="low",
        rationale="Development instance is idle",
        parameters={"simulation": True},
        estimated_monthly_savings_usd="5",
    )


def test_executor_node_processes_policy_decision() -> None:
    proposal = make_proposal()
    decision = PolicyDecision(
        proposal_id=proposal.proposal_id,
        outcome="auto_approved",
        reason_codes=["POLICY_ALLOWED"],
        policy_version="test-policy-v1",
        simulation_allowed=True,
        live_execution_allowed=False,
    )
    executor = SimulatedExecutor(
        audit_repository=InMemoryExecutionAuditRepository(),
        execution_enabled=True,
    )
    executor_node = build_executor_node(executor)

    result = executor_node(
        {
            "proposals": [
                proposal.model_dump(mode="json")
            ],
            "policy_decisions": [
                decision.model_dump(mode="json")
            ],
        }
    )

    assert result["execution_summary"] == {
        "total": 1,
        "simulated": 1,
        "disabled": 0,
        "blocked": 0,
        "actual_aws_calls": 0,
    }
    assert (
        result["execution_records"][0]["status"]
        == "simulated"
    )


def test_executor_node_ignores_missing_proposal() -> None:
    decision = PolicyDecision(
        proposal_id="missing",
        outcome="auto_approved",
        reason_codes=["POLICY_ALLOWED"],
        policy_version="test-policy-v1",
        simulation_allowed=True,
        live_execution_allowed=False,
    )
    executor = SimulatedExecutor(
        audit_repository=InMemoryExecutionAuditRepository(),
        execution_enabled=True,
    )
    executor_node = build_executor_node(executor)

    result = executor_node(
        {
            "proposals": [],
            "policy_decisions": [
                decision.model_dump(mode="json")
            ],
        }
    )

    assert result["execution_summary"]["total"] == 0
    assert result["execution_records"] == []
