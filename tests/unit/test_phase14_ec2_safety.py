from __future__ import annotations

from unittest.mock import MagicMock

from botocore.exceptions import ClientError

from services.phase14.ec2_safety import (
    attached_ebs_monthly_cost,
    attached_elastic_ip_note,
    evaluate_stop_candidate,
    has_termination_protection,
    is_asg_managed,
    is_load_balancer_target,
)


def _client_error(code: str) -> ClientError:
    return ClientError({"Error": {"Code": code, "Message": "boom"}}, "SomeOperation")


def test_is_asg_managed_true_when_instance_present():
    autoscaling = MagicMock()
    autoscaling.describe_auto_scaling_instances.return_value = {"AutoScalingInstances": [{"InstanceId": "i-1"}]}
    assert is_asg_managed(autoscaling, "i-1") is True


def test_is_asg_managed_false_when_empty():
    autoscaling = MagicMock()
    autoscaling.describe_auto_scaling_instances.return_value = {"AutoScalingInstances": []}
    assert is_asg_managed(autoscaling, "i-1") is False


def test_is_asg_managed_fails_safe_to_true_on_error():
    autoscaling = MagicMock()
    autoscaling.describe_auto_scaling_instances.side_effect = _client_error("AccessDenied")
    assert is_asg_managed(autoscaling, "i-1") is True


def test_is_load_balancer_target_finds_match_across_groups():
    elbv2 = MagicMock()
    elbv2.describe_target_groups.return_value = {
        "TargetGroups": [{"TargetGroupArn": "tg-1"}, {"TargetGroupArn": "tg-2"}]
    }

    def health_side_effect(TargetGroupArn):
        if TargetGroupArn == "tg-2":
            return {"TargetHealthDescriptions": [{"Target": {"Id": "i-1"}}]}
        return {"TargetHealthDescriptions": []}

    elbv2.describe_target_health.side_effect = health_side_effect
    assert is_load_balancer_target(elbv2, "i-1") is True


def test_is_load_balancer_target_false_when_no_match():
    elbv2 = MagicMock()
    elbv2.describe_target_groups.return_value = {"TargetGroups": [{"TargetGroupArn": "tg-1"}]}
    elbv2.describe_target_health.return_value = {"TargetHealthDescriptions": [{"Target": {"Id": "i-other"}}]}
    assert is_load_balancer_target(elbv2, "i-1") is False


def test_has_termination_protection_reads_value():
    ec2 = MagicMock()
    ec2.describe_instance_attribute.return_value = {"DisableApiTermination": {"Value": True}}
    assert has_termination_protection(ec2, "i-1") is True


def test_has_termination_protection_fails_safe_to_true_on_error():
    ec2 = MagicMock()
    ec2.describe_instance_attribute.side_effect = _client_error("AccessDenied")
    assert has_termination_protection(ec2, "i-1") is True


def test_attached_ebs_monthly_cost_sums_known_volumes():
    ec2 = MagicMock()
    ec2.describe_volumes.return_value = {"Volumes": [{"VolumeId": "vol-1"}, {"VolumeId": "vol-2"}]}
    cost = attached_ebs_monthly_cost(ec2, "i-1", {"vol-1": 5.0, "vol-2": 3.0})
    assert cost == 8.0


def test_attached_ebs_monthly_cost_none_when_no_volumes():
    ec2 = MagicMock()
    ec2.describe_volumes.return_value = {"Volumes": []}
    assert attached_ebs_monthly_cost(ec2, "i-1", {}) is None


def test_attached_ebs_monthly_cost_none_when_no_matching_cost_data():
    ec2 = MagicMock()
    ec2.describe_volumes.return_value = {"Volumes": [{"VolumeId": "vol-unknown"}]}
    assert attached_ebs_monthly_cost(ec2, "i-1", {"vol-other": 5.0}) is None


def test_attached_elastic_ip_note_present():
    ec2 = MagicMock()
    ec2.describe_addresses.return_value = {"Addresses": [{"PublicIp": "1.2.3.4"}]}
    note = attached_elastic_ip_note(ec2, "i-1")
    assert note is not None
    assert "1.2.3.4" in note


def test_attached_elastic_ip_note_none_when_absent():
    ec2 = MagicMock()
    ec2.describe_addresses.return_value = {"Addresses": []}
    assert attached_elastic_ip_note(ec2, "i-1") is None


def test_evaluate_stop_candidate_excludes_asg_managed():
    ec2 = MagicMock()
    elbv2 = MagicMock()
    autoscaling = MagicMock()
    autoscaling.describe_auto_scaling_instances.return_value = {"AutoScalingInstances": [{"InstanceId": "i-1"}]}
    result = evaluate_stop_candidate(ec2, elbv2, autoscaling, "i-1", {})
    assert result.safe is False
    assert "Auto Scaling" in result.exclusion_reason


def test_evaluate_stop_candidate_excludes_load_balanced():
    ec2 = MagicMock()
    elbv2 = MagicMock()
    autoscaling = MagicMock()
    autoscaling.describe_auto_scaling_instances.return_value = {"AutoScalingInstances": []}
    elbv2.describe_target_groups.return_value = {"TargetGroups": [{"TargetGroupArn": "tg-1"}]}
    elbv2.describe_target_health.return_value = {"TargetHealthDescriptions": [{"Target": {"Id": "i-1"}}]}
    result = evaluate_stop_candidate(ec2, elbv2, autoscaling, "i-1", {})
    assert result.safe is False
    assert "load balancer" in result.exclusion_reason


def test_evaluate_stop_candidate_excludes_termination_protected():
    ec2 = MagicMock()
    elbv2 = MagicMock()
    autoscaling = MagicMock()
    autoscaling.describe_auto_scaling_instances.return_value = {"AutoScalingInstances": []}
    elbv2.describe_target_groups.return_value = {"TargetGroups": []}
    ec2.describe_instance_attribute.return_value = {"DisableApiTermination": {"Value": True}}
    result = evaluate_stop_candidate(ec2, elbv2, autoscaling, "i-1", {})
    assert result.safe is False
    assert "protected" in result.exclusion_reason


def test_evaluate_stop_candidate_safe_with_ebs_and_eip_evidence():
    ec2 = MagicMock()
    elbv2 = MagicMock()
    autoscaling = MagicMock()
    autoscaling.describe_auto_scaling_instances.return_value = {"AutoScalingInstances": []}
    elbv2.describe_target_groups.return_value = {"TargetGroups": []}
    ec2.describe_instance_attribute.return_value = {"DisableApiTermination": {"Value": False}}
    ec2.describe_volumes.return_value = {"Volumes": [{"VolumeId": "vol-1"}]}
    ec2.describe_addresses.return_value = {"Addresses": [{"PublicIp": "1.2.3.4"}]}

    result = evaluate_stop_candidate(ec2, elbv2, autoscaling, "i-1", {"vol-1": 12.5})

    assert result.safe is True
    assert result.evidence["attached_ebs_monthly_cost_usd"] == 12.5
    assert "1.2.3.4" in result.evidence["elastic_ip_note"]
