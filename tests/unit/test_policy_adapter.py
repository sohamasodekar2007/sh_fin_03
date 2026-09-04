from unittest.mock import Mock

from packages.schemas.policy import ActionProposal
from services.policy.policy_adapter import (
    PolicyAdapter,
)


def make_proposal(**changes) -> ActionProposal:
    values = {
        "tenant_id": "tenant-test",
        "snapshot_id": "snapshot-test",
        "resource_id": "i-test123",
        "resource_type": "ec2_instance",
        "action_template": "ec2.stop.v1",
        "environment": "development",
        "risk_level": "low",
        "rationale": "Instance appears idle",
        "parameters": {"dry_run": True},
        "estimated_monthly_savings_usd": "5.00",
    }

    values.update(changes)
    return ActionProposal(**values)


def allowed_result() -> dict:
    return {
        "allowed": True,
        "requires_human_review": False,
        "reason_codes": ["POLICY_ALLOWED"],
        "policy_version": "test-v1",
    }


def test_low_risk_dev_can_auto_approve() -> None:
    evaluator = Mock(return_value=allowed_result())

    adapter = PolicyAdapter(
        evaluator=evaluator,
        execution_enabled=False,
    )

    decision = adapter.evaluate(make_proposal())

    assert decision.outcome == "auto_approved"
    assert decision.simulation_allowed is False
    assert decision.live_execution_allowed is False


def test_production_requires_human() -> None:
    evaluator = Mock(return_value=allowed_result())
    adapter = PolicyAdapter(evaluator=evaluator)

    decision = adapter.evaluate(
        make_proposal(environment="production")
    )

    assert decision.outcome == "human_review"
    assert "PRODUCTION_REQUIRES_HUMAN" in (
        decision.reason_codes
    )


def test_unknown_template_is_blocked() -> None:
    evaluator = Mock(return_value=allowed_result())
    adapter = PolicyAdapter(evaluator=evaluator)

    decision = adapter.evaluate(
        make_proposal(
            action_template="ec2.terminate.v999"
        )
    )

    assert decision.outcome == "blocked"
    assert decision.reason_codes == [
        "UNKNOWN_ACTION_TEMPLATE"
    ]

    evaluator.assert_not_called()


def test_policy_denial_is_blocked() -> None:
    evaluator = Mock(
        return_value={
            "allowed": False,
            "requires_human_review": True,
            "reason_codes": ["POLICY_DENIED"],
            "policy_version": "test-v1",
        }
    )

    adapter = PolicyAdapter(evaluator=evaluator)
    decision = adapter.evaluate(make_proposal())

    assert decision.outcome == "blocked"
    assert decision.simulation_allowed is False


def test_policy_exception_fails_closed() -> None:
    evaluator = Mock(
        side_effect=RuntimeError("engine failed")
    )

    adapter = PolicyAdapter(evaluator=evaluator)
    decision = adapter.evaluate(make_proposal())

    assert decision.outcome == "blocked"
    assert decision.reason_codes == [
        "POLICY_ENGINE_ERROR"
    ]
