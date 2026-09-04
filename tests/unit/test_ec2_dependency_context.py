from __future__ import annotations

from unittest.mock import MagicMock

from botocore.exceptions import ClientError

from packages.schemas.cloud_resource import EC2ResourceRecord
from services.collector.ec2_collector import attach_ec2_dependency_context, _chunked


def _record(instance_id: str, tags: dict[str, str] | None = None) -> EC2ResourceRecord:
    from datetime import datetime, timezone

    return EC2ResourceRecord(
        region="ap-south-1",
        resource_id=instance_id,
        name=instance_id,
        instance_type="t3.micro",
        state="running",
        collected_at=datetime.now(timezone.utc),
        tags=tags or {},
    )


def _client_error(code: str) -> ClientError:
    return ClientError({"Error": {"Code": code, "Message": "boom"}}, "SomeOperation")


def test_chunked_splits_into_size_n_groups():
    assert _chunked(["a", "b", "c", "d", "e"], 2) == [["a", "b"], ["c", "d"], ["e"]]
    assert _chunked([], 2) == []


def test_asg_membership_and_capacity_attached():
    records = [_record("i-1")]
    autoscaling = MagicMock()
    autoscaling.describe_auto_scaling_instances.return_value = {
        "AutoScalingInstances": [{"InstanceId": "i-1", "AutoScalingGroupName": "asg-web"}]
    }
    autoscaling.describe_auto_scaling_groups.return_value = {
        "AutoScalingGroups": [{"AutoScalingGroupName": "asg-web", "DesiredCapacity": 3, "MinSize": 1}]
    }
    elbv2 = MagicMock()
    elbv2.describe_target_groups.return_value = {"TargetGroups": []}
    ec2 = MagicMock()
    ec2.describe_instance_attribute.return_value = {"DisableApiTermination": {"Value": False}}

    attach_ec2_dependency_context(records, autoscaling, elbv2, ec2)

    dep = records[0].dependency_context
    assert dep.in_autoscaling_group == "asg-web"
    assert dep.asg_desired_capacity == 3
    assert dep.asg_min_size == 1
    assert dep.termination_protected is False


def test_not_in_asg_leaves_fields_none():
    records = [_record("i-2")]
    autoscaling = MagicMock()
    autoscaling.describe_auto_scaling_instances.return_value = {"AutoScalingInstances": []}
    elbv2 = MagicMock()
    elbv2.describe_target_groups.return_value = {"TargetGroups": []}
    ec2 = MagicMock()
    ec2.describe_instance_attribute.return_value = {"DisableApiTermination": {"Value": False}}

    attach_ec2_dependency_context(records, autoscaling, elbv2, ec2)

    dep = records[0].dependency_context
    assert dep.in_autoscaling_group is None
    assert dep.asg_desired_capacity is None
    assert dep.asg_min_size is None


def test_load_balancer_target_membership_across_groups():
    records = [_record("i-3")]
    autoscaling = MagicMock()
    autoscaling.describe_auto_scaling_instances.return_value = {"AutoScalingInstances": []}
    elbv2 = MagicMock()
    elbv2.describe_target_groups.return_value = {
        "TargetGroups": [{"TargetGroupArn": "tg-1"}, {"TargetGroupArn": "tg-2"}]
    }

    def health_side_effect(TargetGroupArn):
        if TargetGroupArn == "tg-2":
            return {"TargetHealthDescriptions": [{"Target": {"Id": "i-3"}}]}
        return {"TargetHealthDescriptions": []}

    elbv2.describe_target_health.side_effect = health_side_effect
    ec2 = MagicMock()
    ec2.describe_instance_attribute.return_value = {"DisableApiTermination": {"Value": False}}

    attach_ec2_dependency_context(records, autoscaling, elbv2, ec2)

    assert records[0].dependency_context.load_balancer_targets == ["tg-2"]


def test_termination_protection_read():
    records = [_record("i-4")]
    autoscaling = MagicMock()
    autoscaling.describe_auto_scaling_instances.return_value = {"AutoScalingInstances": []}
    elbv2 = MagicMock()
    elbv2.describe_target_groups.return_value = {"TargetGroups": []}
    ec2 = MagicMock()
    ec2.describe_instance_attribute.return_value = {"DisableApiTermination": {"Value": True}}

    attach_ec2_dependency_context(records, autoscaling, elbv2, ec2)

    assert records[0].dependency_context.termination_protected is True


def test_termination_protection_fails_safe_to_true_on_error():
    records = [_record("i-5")]
    autoscaling = MagicMock()
    autoscaling.describe_auto_scaling_instances.return_value = {"AutoScalingInstances": []}
    elbv2 = MagicMock()
    elbv2.describe_target_groups.return_value = {"TargetGroups": []}
    ec2 = MagicMock()
    ec2.describe_instance_attribute.side_effect = _client_error("AccessDenied")

    attach_ec2_dependency_context(records, autoscaling, elbv2, ec2)

    assert records[0].dependency_context.termination_protected is True


def test_missing_ownership_true_when_no_owner_or_environment_tag():
    records = [_record("i-6", tags={"Name": "web"})]
    autoscaling = MagicMock()
    autoscaling.describe_auto_scaling_instances.return_value = {"AutoScalingInstances": []}
    elbv2 = MagicMock()
    elbv2.describe_target_groups.return_value = {"TargetGroups": []}
    ec2 = MagicMock()
    ec2.describe_instance_attribute.return_value = {"DisableApiTermination": {"Value": False}}

    attach_ec2_dependency_context(records, autoscaling, elbv2, ec2)

    assert records[0].dependency_context.missing_ownership is True


def test_missing_ownership_false_when_owner_tag_present():
    records = [_record("i-7", tags={"Owner": "alice"})]
    autoscaling = MagicMock()
    autoscaling.describe_auto_scaling_instances.return_value = {"AutoScalingInstances": []}
    elbv2 = MagicMock()
    elbv2.describe_target_groups.return_value = {"TargetGroups": []}
    ec2 = MagicMock()
    ec2.describe_instance_attribute.return_value = {"DisableApiTermination": {"Value": False}}

    attach_ec2_dependency_context(records, autoscaling, elbv2, ec2)

    assert records[0].dependency_context.missing_ownership is False


def test_empty_records_is_a_noop():
    autoscaling = MagicMock()
    elbv2 = MagicMock()
    ec2 = MagicMock()
    attach_ec2_dependency_context([], autoscaling, elbv2, ec2)
    autoscaling.describe_auto_scaling_instances.assert_not_called()


def test_asg_membership_lookup_failure_degrades_gracefully():
    records = [_record("i-8")]
    autoscaling = MagicMock()
    autoscaling.describe_auto_scaling_instances.side_effect = _client_error("AccessDenied")
    elbv2 = MagicMock()
    elbv2.describe_target_groups.return_value = {"TargetGroups": []}
    ec2 = MagicMock()
    ec2.describe_instance_attribute.return_value = {"DisableApiTermination": {"Value": False}}

    # Must not raise — degrades to "no ASG info" instead.
    attach_ec2_dependency_context(records, autoscaling, elbv2, ec2)

    assert records[0].dependency_context.in_autoscaling_group is None
