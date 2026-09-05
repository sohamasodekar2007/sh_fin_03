"""
Unit test for merged Analyzer Agent (Detect) - rule engine and observation processing.
"""

from services.collector.mock_provider import generate_mock_observation_bundle
from services.analyzer.service import analyze_observation
from services.focus.mappers.aws import map_snapshot_to_focus


def test_analyzer_agent_rule_execution():
    """Verify Analyzer Agent detects findings from Monitor Agent observation bundle."""
    snapshot = generate_mock_observation_bundle(account_id="123456789012", region="us-east-1")
    observation_dict = snapshot.model_dump(mode="json")

    findings = analyze_observation(observation_dict)

    assert isinstance(findings, list)
    assert len(findings) > 0

    rule_ids = [f["rule_id"] for f in findings]

    # Verify key rules triggered
    assert "ec2.idle.v1" in rule_ids
    assert "ec2.overprovisioned.v1" in rule_ids
    assert "ebs.unattached.v1" in rule_ids
    assert "cost.anomaly.v1" in rule_ids

    # Verify structure of finding
    first_finding = findings[0]
    assert "resource_id" in first_finding
    assert "rule_id" in first_finding
    assert "severity" in first_finding
    assert "confidence" in first_finding
    assert "evidence" in first_finding


def test_analyzer_agent_detects_live_aws_service_configuration_findings():
    observation = {
        "account_id": "123456789012",
        "region": "ap-south-1",
        "collected_at": "2026-09-05T00:00:00+00:00",
        "status": "success",
        "resources": [
            {
                "resource_id": "cloudcare-demo-postgres",
                "resource_type": "rds_instance",
                "region": "ap-south-1",
                "environment": "development",
                "state": "available",
                "engine": "postgres",
                "storage_encrypted": True,
                "publicly_accessible": False,
                "dependency_context": {"multi_az": False, "deletion_protection": False},
                "tags": {"Environment": "dev"},
            },
            {
                "resource_id": "cloudcare-demo-orders",
                "resource_type": "dynamodb_table",
                "region": "ap-south-1",
                "environment": "development",
                "state": "active",
                "billing_mode": "PAY_PER_REQUEST",
                "point_in_time_recovery_enabled": False,
                "tags": {"Environment": "dev"},
            },
            {
                "resource_id": "cloudcare-demo-optimizer-sample",
                "resource_type": "lambda_function",
                "region": "ap-south-1",
                "environment": "development",
                "state": "active",
                "runtime": "python3.12",
                "timeout_seconds": 120,
                "vpc_config_present": True,
                "tags": {"Environment": "dev"},
            },
            {
                "resource_id": "sg-1",
                "resource_type": "security_group",
                "region": "ap-south-1",
                "environment": "development",
                "state": "active",
                "ingress_rules": [
                    {"protocol": "tcp", "from_port": 5432, "to_port": 5432, "cidr": "0.0.0.0/0"},
                ],
                "tags": {"Environment": "dev"},
            },
        ],
        "cpu_metrics": [],
        "daily_costs": [],
    }

    findings = analyze_observation(observation)
    rule_ids = {finding["rule_id"] for finding in findings}

    assert "rds.single_az.v1" in rule_ids
    assert "rds.deletion_protection_disabled.v1" in rule_ids
    assert "dynamodb.pitr_disabled.v1" in rule_ids
    assert "lambda.long_timeout.v1" in rule_ids
    assert "sg.open_ingress.v1" in rule_ids

    focus_dataset = map_snapshot_to_focus(observation, tenant_id="demo-tenant")
    focus_findings = analyze_observation(focus_dataset)
    focus_rule_ids = {finding["rule_id"] for finding in focus_findings}

    assert "rds.single_az.v1" in focus_rule_ids
    assert "rds.deletion_protection_disabled.v1" in focus_rule_ids
    assert "dynamodb.pitr_disabled.v1" in focus_rule_ids
    assert "lambda.long_timeout.v1" in focus_rule_ids
    assert "sg.open_ingress.v1" in focus_rule_ids
