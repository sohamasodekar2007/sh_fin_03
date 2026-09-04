import sys
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parents[1]

if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from services.executor.execution_audit import (
    InMemoryExecutionAuditRepository,
)
from packages.schemas.policy import (
    ActionProposal,
    PolicyDecision,
)
from services.executor.simulated_executor import (
    SimulatedExecutor,
)


def main() -> None:
    repository = (
        InMemoryExecutionAuditRepository()
    )

    executor = SimulatedExecutor(
        audit_repository=repository,
        execution_enabled=True,
        execution_mode="simulation",
    )

    proposal = ActionProposal(
        proposal_id="proposal-demo-001",
        tenant_id="tenant-demo",
        snapshot_id="snapshot-demo",
        resource_id="i-example123",
        resource_type="ec2_instance",
        action_template="ec2.stop.v1",
        environment="development",
        risk_level="low",
        rationale="Development instance appears idle",
        parameters={
            "simulation": True
        },
        estimated_monthly_savings_usd="5.00",
    )

    decision = PolicyDecision(
        proposal_id=proposal.proposal_id,
        outcome="auto_approved",
        reason_codes=[
            "LOW_RISK_DEV_APPROVED"
        ],
        policy_version="demo-policy-v1",
        simulation_allowed=True,
        live_execution_allowed=False,
    )

    first_result = executor.execute(
        proposal,
        decision,
    )

    second_result = executor.execute(
        proposal,
        decision,
    )

    print("First execution:")
    print(first_result.model_dump_json(indent=2))

    print("\nDuplicate execution:")
    print(second_result.model_dump_json(indent=2))

    print(
        "\nAudit record count:",
        repository.count(),
    )

    print(
        "Same execution ID:",
        first_result.execution_id
        == second_result.execution_id,
    )


if __name__ == "__main__":
    main()
