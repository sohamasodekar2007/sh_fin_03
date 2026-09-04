from datetime import datetime, timezone

from services.collector.ec2_collector import (
    normalize_environment,
    normalize_instance,
    normalize_volume,
    tags_to_dictionary,
)


def test_tags_to_dictionary():
    tags = [
        {
            "Key": "Name",
            "Value": "cloudcare-demo",
        },
        {
            "Key": "Environment",
            "Value": "dev",
        },
    ]

    result = tags_to_dictionary(tags)

    assert result == {
        "Name": "cloudcare-demo",
        "Environment": "dev",
    }


def test_environment_alias():
    tags = {
        "Environment": "DEV",
    }

    assert normalize_environment(tags) == "development"


def test_missing_environment_is_unknown():
    tags = {
        "Name": "cloudcare-demo",
    }

    assert normalize_environment(tags) == "unknown"


def test_normalize_instance():
    instance = {
        "InstanceId": "i-test123",
        "InstanceType": "t3.micro",
        "State": {
            "Name": "running",
        },
        "Placement": {
            "AvailabilityZone": "ap-south-1a",
        },
        "Tags": [
            {
                "Key": "Name",
                "Value": "cloudcare-demo",
            },
            {
                "Key": "Environment",
                "Value": "development",
            },
        ],
        "PrivateIpAddress": "10.0.0.10",
        "VpcId": "vpc-test",
        "SubnetId": "subnet-test",
    }

    result = normalize_instance(
        instance=instance,
        region="ap-south-1",
        collected_at=datetime.now(timezone.utc),
    )

    assert result.resource_id == "i-test123"
    assert result.name == "cloudcare-demo"
    assert result.environment == "development"
    assert result.state == "running"


def test_normalize_volume_unattached_flags_warning():
    volume = {
        "VolumeId": "vol-test123",
        "Size": 500,
        "VolumeType": "gp3",
        "State": "available",
        "AvailabilityZone": "ap-south-1b",
        "Tags": [{"Key": "Name", "Value": "unused-backup-vol"}],
    }

    result = normalize_volume(
        volume=volume,
        region="ap-south-1",
        collected_at=datetime.now(timezone.utc),
    )

    assert result.resource_id == "vol-test123"
    assert result.resource_type == "ebs_volume"
    assert result.instance_type == "500GB-gp3"
    assert result.state == "available"
    assert "UNATTACHED_EBS_VOLUME" in result.warnings


def test_normalize_volume_attached_has_no_unattached_warning():
    volume = {
        "VolumeId": "vol-test456",
        "Size": 100,
        "VolumeType": "gp2",
        "State": "in-use",
        "Tags": [],
    }

    result = normalize_volume(
        volume=volume,
        region="ap-south-1",
        collected_at=datetime.now(timezone.utc),
    )

    assert result.state == "in-use"
    assert "UNATTACHED_EBS_VOLUME" not in result.warnings
    assert "RESOURCE_HAS_NO_TAGS" in result.warnings
