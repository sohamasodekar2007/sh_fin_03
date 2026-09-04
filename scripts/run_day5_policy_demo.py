import sys
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parents[1]

if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from packages.schemas.policy import ActionProposal
from services.policy.policy_adapter import (
    PolicyAdapter,
)


def fake_existing_policy_engine(
    proposal: dict,
) -> dict:
    return {
        "allowed": True,
        "requires_human_review": False,
        "reason_codes": [
            "LOW_RISK_DEV_RESOURCE"
        ],
        "policy_version": "demo-policy-v1",
    }


def main() -> None:
    adapter = PolicyAdapter(
        evaluator=fake_existing_policy_engine,
        execution_enabled=False,
        execution_mode="simulation",
    )

    proposal = ActionProposal(
        tenant_id="tenant-demo",
        snapshot_id="snapshot-demo",
        resource_id="i-example123",
        resource_type="ec2_instance",
        action_template="ec2.stop.v1",
        environment="development",
        risk_level="low",
        rationale=(
            "Development instance has remained idle."
        ),
        parameters={
            "dry_run": True
        },
        estimated_monthly_savings_usd="4.25",
    )

    decision = adapter.evaluate(proposal)

    print(decision.model_dump_json(indent=2))


if __name__ == "__main__":
    main()
