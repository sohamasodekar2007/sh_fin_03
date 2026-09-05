from apps.api.routers import resources


def test_tag_savings_aggregates_live_instance_proposals_by_tag(monkeypatch):
    snapshot = {
        "account_id": "123456789012",
        "region": "ap-south-1",
        "resource_count": 2,
        "resources": [
            {"resource_id": "i-dev", "resource_type": "ec2_instance", "instance_type": "t3.micro", "state": "running", "tags": {"Environment": "dev"}},
            {"resource_id": "i-untagged", "resource_type": "ec2_instance", "instance_type": "t3.micro", "state": "stopped", "tags": {}},
        ],
    }
    proposals = [
        {
            "resource_id": "i-dev",
            "resource_name": "dev-api",
            "resource_type": "ec2_instance",
            "resource_arn": "arn:aws:ec2:ap-south-1:123456789012:instance/i-dev",
            "parameters": {"instance_id": "i-dev"},
            "tags": {"Environment": "dev"},
            "action_type": "stop_instance",
            "risk_level": "low",
            "expected_monthly_savings": "300",
        },
        {
            "resource_id": "i-dev",
            "resource_name": "dev-api",
            "resource_type": "ec2_instance",
            "resource_arn": "arn:aws:ec2:ap-south-1:123456789012:instance/i-dev",
            "parameters": {"instance_id": "i-dev"},
            "tags": {"Environment": "dev"},
            "action_type": "resize_instance",
            "risk_level": "medium",
            "expected_monthly_savings": "120",
        },
        {
            "resource_id": "i-untagged",
            "resource_name": "worker",
            "resource_type": "ec2_instance",
            "resource_arn": "arn:aws:ec2:ap-south-1:123456789012:instance/i-untagged",
            "parameters": {"instance_id": "i-untagged"},
            "tags": {},
            "action_type": "stop_instance",
            "risk_level": "high",
            "expected_monthly_savings": "300",
        },
    ]

    monkeypatch.setattr(resources, "analyze_observation", lambda _snapshot: [{"rule_id": "ec2.idle.v1"}])
    monkeypatch.setattr(resources, "build_proposals", lambda _snapshot, _findings: proposals)

    result = resources._tag_savings_from_snapshot(snapshot, "Environment")

    assert result.monthly_savings == 720
    assert [(group.tag_value, group.instances, group.monthly_savings) for group in result.groups] == [
        ("dev", 1, 420),
        ("untagged", 1, 300),
    ]
    assert [(row.instance_id, row.actions, row.risk, row.monthly_savings) for row in result.instances] == [
        ("i-dev", ["resize_instance", "stop_instance"], "medium", 420),
        ("i-untagged", ["stop_instance"], "high", 300),
    ]
    assert [(row.instance_id, row.instance_type, row.vcpu, row.memory_gib, row.state) for row in result.instances] == [
        ("i-dev", "t3.micro", 2, 1.0, "running"),
        ("i-untagged", "t3.micro", 2, 1.0, "stopped"),
    ]
    assert result.available_tag_keys == ["Environment"]
