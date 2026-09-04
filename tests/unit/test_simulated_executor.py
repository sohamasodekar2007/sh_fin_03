import ast
from pathlib import Path

import pytest
from pydantic import ValidationError

from services.executor.execution_audit import (
    InMemoryExecutionAuditRepository,
)
from packages.schemas.execution import ExecutionRecord
from packages.schemas.policy import (
    ActionProposal,
    PolicyDecision,
)
from services.executor.simulated_executor import (
    SimulatedExecutor,
)


def make_proposal(**changes) -> ActionProposal:
    values = {
        "proposal_id": "proposal-test-001",
        "tenant_id": "tenant-test",
        "snapshot_id": "snapshot-test",
        "resource_id": "i-test123",
        "resource_type": "ec2_instance",
        "action_template": "ec2.stop.v1",
        "environment": "development",
        "risk_level": "low",
        "rationale": "Development instance is idle",
        "parameters": {"simulation": True},
        "estimated_monthly_savings_usd": "5",
    }

    values.update(changes)
    return ActionProposal(**values)


def make_decision(
    proposal: ActionProposal,
    **changes,
) -> PolicyDecision:
    values = {
        "proposal_id": proposal.proposal_id,
        "outcome": "auto_approved",
        "reason_codes": ["POLICY_ALLOWED"],
        "policy_version": "test-policy-v1",
        "simulation_allowed": True,
        "live_execution_allowed": False,
    }

    values.update(changes)
    return PolicyDecision(**values)


def make_executor(
    execution_enabled: bool = True,
) -> SimulatedExecutor:
    return SimulatedExecutor(
        audit_repository=InMemoryExecutionAuditRepository(),
        execution_enabled=execution_enabled,
        execution_mode="simulation",
    )


def test_simulation_makes_no_aws_call() -> None:
    proposal = make_proposal()
    decision = make_decision(proposal)
    executor = make_executor()

    result = executor.execute(proposal, decision)

    assert result.status == "simulated"
    assert result.actual_aws_call_made is False
    assert result.verification["aws_state_changed"] is False
    assert result.would_execute["operation"] == "StopInstances"


def test_duplicate_request_returns_same_record() -> None:
    repository = InMemoryExecutionAuditRepository()
    executor = SimulatedExecutor(
        audit_repository=repository,
        execution_enabled=True,
    )
    proposal = make_proposal()
    decision = make_decision(proposal)

    first = executor.execute(proposal, decision)
    second = executor.execute(proposal, decision)

    assert first.execution_id == second.execution_id
    assert repository.count() == 1


def test_kill_switch_disables_execution() -> None:
    proposal = make_proposal()
    decision = make_decision(proposal)
    executor = make_executor(execution_enabled=False)

    result = executor.execute(proposal, decision)

    assert result.status == "disabled"
    assert result.reason_codes == [
        "EXECUTION_KILL_SWITCH_ACTIVE"
    ]
    assert result.actual_aws_call_made is False


def test_human_review_is_not_executed() -> None:
    proposal = make_proposal()
    decision = make_decision(
        proposal,
        outcome="human_review",
        simulation_allowed=False,
    )
    executor = make_executor()

    result = executor.execute(proposal, decision)

    assert result.status == "blocked"
    assert result.reason_codes == [
        "PROPOSAL_NOT_AUTO_APPROVED"
    ]


def test_production_is_blocked_defense_in_depth() -> None:
    proposal = make_proposal(environment="production")
    decision = make_decision(proposal)
    executor = make_executor()

    result = executor.execute(proposal, decision)

    assert result.status == "blocked"
    assert result.reason_codes == [
        "PRODUCTION_EXECUTION_BLOCKED"
    ]


def test_live_execution_flag_is_rejected() -> None:
    proposal = make_proposal()
    decision = make_decision(
        proposal,
        live_execution_allowed=True,
    )
    executor = make_executor()

    result = executor.execute(proposal, decision)

    assert result.status == "blocked"
    assert result.reason_codes == [
        "LIVE_EXECUTION_FORBIDDEN"
    ]


def test_execution_record_rejects_true_aws_call_flag() -> None:
    with pytest.raises(ValidationError):
        ExecutionRecord(
            idempotency_key="key",
            proposal_id="proposal",
            tenant_id="tenant",
            resource_id="i-test",
            resource_type="ec2_instance",
            environment="development",
            action_template="ec2.stop.v1",
            status="simulated",
            policy_version="test",
            actual_aws_call_made=True,
        )


def test_executor_module_does_not_import_boto3() -> None:
    source_path = (
        Path(__file__).resolve().parents[2]
        / "services"
        / "executor"
        / "simulated_executor.py"
    )
    module = ast.parse(source_path.read_text())

    imported_names = []
    for node in ast.walk(module):
        if isinstance(node, ast.Import):
            imported_names.extend(
                alias.name for alias in node.names
            )
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported_names.append(node.module)

    assert "boto3" not in imported_names
