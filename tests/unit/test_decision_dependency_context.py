from __future__ import annotations

from services.decision.service import build_proposals


def _observation(resource: dict, account_id: str = "123456789012") -> dict:
    return {"account_id": account_id, "resources": [resource]}


def _idle_finding(resource_id: str = "i-1", confidence: float = 0.9) -> dict:
    return {
        "resource_id": resource_id,
        "rule_id": "ec2.idle.v1",
        "confidence": confidence,
        "evidence": {"cpu_p95": 1.2, "network_p95_bytes": 500},
    }


def _resource(resource_id: str = "i-1", environment: str = "dev", tags: dict | None = None, dep_ctx: dict | None = None) -> dict:
    return {
        "resource_id": resource_id,
        "instance_id": resource_id,
        "environment": environment,
        "region": "ap-south-1",
        "resource_type": "ec2_instance",
        "monthly_cost_usd": 100.0,
        "tags": tags or {},
        "dependency_context": dep_ctx or {},
    }


# ---------------------------------------------------------------------------
# ASG-managed idle instance
# ---------------------------------------------------------------------------


def test_asg_managed_with_room_to_shrink_proposes_adjust_asg_capacity():
    resource = _resource(dep_ctx={
        "in_autoscaling_group": "asg-web", "asg_desired_capacity": 3, "asg_min_size": 1,
    })
    proposals = build_proposals(_observation(resource), [_idle_finding()])

    assert len(proposals) == 1
    p = proposals[0]
    assert p["action_type"] == "adjust_asg_capacity"
    assert p["template_id"] == "asg.adjust_capacity.v1"
    assert p["parameters"]["asg_name"] == "asg-web"
    assert p["parameters"]["proposed_desired_capacity"] == 2
    assert p["requires_human_approval"] is True  # not auto-executable yet, regardless of env/risk
    assert "asg-web" in p["rationale"]
    assert "never a plain stop" not in p["rationale"]  # sanity: no leftover placeholder text


def test_asg_managed_already_at_minimum_proposes_no_action():
    resource = _resource(dep_ctx={
        "in_autoscaling_group": "asg-web", "asg_desired_capacity": 1, "asg_min_size": 1,
    })
    proposals = build_proposals(_observation(resource), [_idle_finding()])

    assert len(proposals) == 1
    p = proposals[0]
    assert p["action_type"] == "no_action"
    assert p["template_id"] == "ec2.no_action.v1"
    assert float(p["expected_monthly_savings"]) == 0.0
    assert "minimum capacity" in p["rationale"]


def test_asg_managed_never_produces_plain_stop_instance():
    resource = _resource(dep_ctx={
        "in_autoscaling_group": "asg-web", "asg_desired_capacity": 5, "asg_min_size": 2,
    })
    proposals = build_proposals(_observation(resource), [_idle_finding()])

    assert all(p["action_type"] != "stop_instance" for p in proposals)


# ---------------------------------------------------------------------------
# Termination-protected idle instance
# ---------------------------------------------------------------------------


def test_termination_protected_proposes_no_action_not_dropped():
    resource = _resource(dep_ctx={"termination_protected": True})
    proposals = build_proposals(_observation(resource), [_idle_finding()])

    # Visible in the UI, never silently vanished.
    assert len(proposals) == 1
    p = proposals[0]
    assert p["action_type"] == "no_action"
    assert p["requires_human_approval"] is False
    assert "protected" in p["rationale"].lower()


# ---------------------------------------------------------------------------
# Load-balancer-targeted idle instance
# ---------------------------------------------------------------------------


def test_load_balancer_target_floors_risk_at_medium_and_stays_stop_instance():
    resource = _resource(environment="dev", dep_ctx={"load_balancer_targets": ["tg-1"]})
    proposals = build_proposals(_observation(resource), [_idle_finding()])

    assert len(proposals) == 1
    p = proposals[0]
    assert p["action_type"] == "stop_instance"
    assert p["risk_level"] == "medium"  # dev would normally be "low"
    assert "live traffic" in p["rationale"]


def test_load_balancer_target_does_not_lower_an_already_higher_risk():
    resource = _resource(environment="prod", dep_ctx={"load_balancer_targets": ["tg-1"]})
    proposals = build_proposals(_observation(resource), [_idle_finding()])

    assert proposals[0]["risk_level"] == "high"  # prod's "high" is above the "medium" floor


# ---------------------------------------------------------------------------
# No dependency context at all — unchanged, plain stop_instance
# ---------------------------------------------------------------------------


def test_no_dependency_context_is_unchanged_plain_stop_instance():
    resource = _resource(tags={"Environment": "dev", "Team": "platform"})
    resource["name"] = "idle-api"
    proposals = build_proposals(_observation(resource), [_idle_finding()])

    assert len(proposals) == 1
    p = proposals[0]
    assert p["action_type"] == "stop_instance"
    assert p["template_id"] == "ec2.stop.v1"
    assert p["risk_level"] == "low"
    assert p["requires_human_approval"] is False
    assert p["resource_id"] == "i-1"
    assert p["resource_name"] == "idle-api"
    assert p["resource_type"] == "ec2_instance"
    assert p["tags"] == {"Environment": "dev", "Team": "platform"}


# ---------------------------------------------------------------------------
# missing_ownership — universal floor, applies regardless of action_type
# ---------------------------------------------------------------------------


def test_missing_ownership_forces_human_approval_on_plain_stop():
    resource = _resource(environment="dev", dep_ctx={"missing_ownership": True})
    proposals = build_proposals(_observation(resource), [_idle_finding()])

    assert proposals[0]["requires_human_approval"] is True
    assert "ownership" in proposals[0]["rationale"].lower()


def test_missing_ownership_forces_human_approval_on_delete_volume():
    resource = _resource(resource_id="vol-1", environment="dev", dep_ctx={"missing_ownership": True})
    finding = {
        "resource_id": "vol-1", "rule_id": "ebs.unattached.v1",
        "confidence": 0.9, "evidence": {"unattached_hours": 48},
    }
    proposals = build_proposals(_observation(resource), [finding])

    assert proposals[0]["action_type"] == "delete_volume"
    assert proposals[0]["requires_human_approval"] is True


# ---------------------------------------------------------------------------
# cloudcare:max-risk — approval floor, never overwrites risk_level itself
# ---------------------------------------------------------------------------


def test_max_risk_ceiling_caps_risk_level_and_forces_approval():
    resource = _resource(environment="prod", tags={"cloudcare:max-risk": "low"})
    proposals = build_proposals(_observation(resource), [_idle_finding()])

    p = proposals[0]
    assert p["risk_level"] == "low"
    assert p["requires_human_approval"] is True
    assert "max-risk" in p["rationale"]
    assert "risk_level high" in p["rationale"]
    assert "cloudcare:max-risk=low" in p["dependency_facts"]


def test_max_risk_ceiling_not_exceeded_has_no_effect():
    resource = _resource(environment="dev", tags={"cloudcare:max-risk": "high"})
    proposals = build_proposals(_observation(resource), [_idle_finding()])

    p = proposals[0]
    assert p["risk_level"] == "low"
    assert p["requires_human_approval"] is False


def test_cloudcare_exclude_true_blocks_proposal_even_if_finding_reaches_decision():
    resource = _resource(environment="dev", tags={"cloudcare:exclude": "true"})
    proposals = build_proposals(_observation(resource), [_idle_finding()])

    assert proposals == []


def test_rationale_always_names_dependency_facts_considered():
    resource = _resource()
    proposals = build_proposals(_observation(resource), [_idle_finding()])

    rationale = proposals[0]["rationale"]
    assert "Dependency facts considered:" in rationale
    assert "asg=none" in rationale
    assert "load_balancer_targets=0" in rationale
    assert "termination_protected=false" in rationale
    assert "ownership=present_or_not_reported" in rationale


def test_service_configuration_finding_becomes_audit_review_proposal():
    resource = {
        "resource_id": "cloudcare-demo-orders",
        "environment": "dev",
        "region": "ap-south-1",
        "resource_type": "dynamodb_table",
        "monthly_cost_usd": 0.0,
        "tags": {"Environment": "dev"},
    }
    finding = {
        "resource_id": "cloudcare-demo-orders",
        "rule_id": "dynamodb.pitr_disabled.v1",
        "confidence": 0.93,
        "evidence": {"point_in_time_recovery_enabled": False},
    }

    proposals = build_proposals(_observation(resource), [finding])

    assert len(proposals) == 1
    p = proposals[0]
    assert p["action_type"] == "review_finding"
    assert p["template_id"] == "aws.audit_review.v1"
    assert p["parameters"]["resource_id"] == "cloudcare-demo-orders"
    assert p["parameters"]["resource_type"] == "dynamodb_table"
    assert p["parameters"]["rule_id"] == "dynamodb.pitr_disabled.v1"
    assert float(p["expected_monthly_savings"]) == 0.0
