from __future__ import annotations

from datetime import datetime, timedelta, timezone
from decimal import Decimal

from services.focus.metrics import ResourceMetric
from services.supervisor.service import evaluate_policy_outcome, score_proposal


def _proposal(
    action_type: str = "stop_instance",
    template_id: str = "ec2.stop.v1",
    risk_level: str = "low",
    savings: str = "42.00",
    rollback_plan: dict | None = None,
) -> dict:
    return {
        "proposal_id": "p1",
        "resource_arn": "arn:aws:ec2:ap-south-1:demo:instance/i-1",
        "action_type": action_type,
        "template_id": template_id,
        "parameters": {"instance_id": "i-1", "region": "ap-south-1"},
        "expected_monthly_savings": savings,
        "risk_level": risk_level,
        "confidence": 0.8,
        "evidence": [{"metric": "cpu_p95", "value": 2.0, "window_days": 14}],
        "rollback_plan": rollback_plan if rollback_plan is not None else ({"template_id": "ec2.start.v1"} if action_type == "stop_instance" else None),
        "requires_human_approval": True,
        "status": "proposed",
        "rationale": "idle instance detected",
    }


# ---------------------------------------------------------------------------
# (a) A production resource is never auto-approved.
# ---------------------------------------------------------------------------


def test_production_resource_is_never_auto_approved():
    proposal = _proposal(risk_level="low")  # the most auto-execute-friendly risk level

    outcome, _reason_codes = evaluate_policy_outcome(
        proposal, tenant_id="demo-tenant", environment_long="production", has_owner_tag=True, is_protected=False
    )

    assert outcome != "auto_approved"


def test_non_production_low_risk_owned_resource_can_be_auto_approved():
    """Sanity check for the test above: dev/staging genuinely CAN come back
    auto_approved — proving the production test isn't just "always
    needs_approval" for every input."""
    proposal = _proposal(risk_level="low")

    outcome, _reason_codes = evaluate_policy_outcome(
        proposal, tenant_id="demo-tenant", environment_long="development", has_owner_tag=True, is_protected=False
    )

    assert outcome == "auto_approved"


def test_unknown_action_template_is_blocked():
    proposal = _proposal(action_type="resize_instance", template_id="ec2.resize.v1")

    outcome, reason_codes = evaluate_policy_outcome(
        proposal, tenant_id="demo-tenant", environment_long="development", has_owner_tag=True, is_protected=False
    )

    assert outcome == "blocked"
    assert reason_codes


# ---------------------------------------------------------------------------
# (b) Scores are within [0, 1].
# ---------------------------------------------------------------------------


def test_confidence_and_risk_scores_are_within_zero_and_one():
    now = datetime.now(timezone.utc)
    metric = ResourceMetric(
        resource_id="i-1",
        tenant_id="demo-tenant",
        window_start=now - timedelta(days=14),
        window_end=now - timedelta(hours=1),
        cpu_p95=2.0,
        sample_count=14,
    )

    for risk_level in ("low", "medium", "high", "critical"):
        for environment_long in ("development", "staging", "production", "unknown"):
            for action_type in ("stop_instance", "resize_instance"):
                proposal = _proposal(action_type=action_type, risk_level=risk_level)
                score = score_proposal(proposal, resource=None, resource_metric=metric, environment_long=environment_long, now=now)
                assert 0.0 <= score["confidence_score"] <= 1.0
                assert 0.0 <= score["risk_score"] <= 1.0


def test_confidence_score_with_no_metric_still_within_bounds():
    proposal = _proposal()
    score = score_proposal(proposal, resource=None, resource_metric=None, environment_long="development")
    assert 0.0 <= score["confidence_score"] <= 1.0
    assert 0.0 <= score["risk_score"] <= 1.0


def test_production_scores_higher_risk_than_development_for_the_same_proposal():
    proposal = _proposal(risk_level="low")
    dev_score = score_proposal(proposal, resource=None, resource_metric=None, environment_long="development")
    prod_score = score_proposal(proposal, resource=None, resource_metric=None, environment_long="production")
    assert prod_score["risk_score"] > dev_score["risk_score"]


# ---------------------------------------------------------------------------
# (c) Savings arithmetic is exact with Decimal.
# ---------------------------------------------------------------------------


def test_savings_arithmetic_is_exact_with_decimal():
    resource = {"monthly_cost_usd": 100.10}
    proposal = _proposal(savings="33.33")

    score = score_proposal(proposal, resource=resource, resource_metric=None, environment_long="development")

    assert score["cost_current_monthly"] == "100.10"
    assert score["savings_monthly"] == "33.33"
    # 100.10 - 33.33 = 66.77 exactly — this fails under naive float
    # arithmetic (100.10 - 33.33 == 66.77000000000001 in binary float).
    assert score["cost_optimized_monthly"] == "66.77"
    assert Decimal(score["cost_current_monthly"]) - Decimal(score["savings_monthly"]) == Decimal(
        score["cost_optimized_monthly"]
    )
    # 33.33 * 12 = 399.96 exactly.
    assert score["savings_annual"] == "399.96"


def test_savings_never_pushes_optimized_cost_below_zero():
    resource = {"monthly_cost_usd": 10.00}
    proposal = _proposal(savings="42.00")  # larger than the resource's own cost

    score = score_proposal(proposal, resource=resource, resource_metric=None, environment_long="development")

    assert score["cost_optimized_monthly"] == "0.00"
