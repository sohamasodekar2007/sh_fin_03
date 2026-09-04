"""
Unit test for Monitor Agent (Observe) - Mock Data Provider & Observation Bundle Schema.
"""

from services.collector.mock_provider import generate_mock_observation_bundle
from packages.schemas.cloud_snapshot import CloudSnapshot


def test_monitor_agent_mock_observation_bundle():
    """Verify Monitor Agent produces valid CloudSnapshot observation bundle with 24 resources."""
    snapshot = generate_mock_observation_bundle(account_id="123456789012", region="us-east-1")

    assert isinstance(snapshot, CloudSnapshot)
    assert snapshot.account_id == "123456789012"
    assert snapshot.region == "us-east-1"
    assert snapshot.status == "success"

    # Verify resource count & mix
    assert snapshot.resource_count == 24
    assert len(snapshot.resources) == 24

    # Verify EC2 vs EBS volumes
    ec2_resources = [r for r in snapshot.resources if r.get("resource_type") == "ec2_instance"]
    ebs_resources = [r for r in snapshot.resources if r.get("resource_type") == "ebs_volume"]
    assert len(ec2_resources) == 20
    assert len(ebs_resources) == 4

    # Verify CloudWatch metrics
    assert snapshot.metric_count == 20
    assert len(snapshot.cpu_metrics) == 20

    # Verify 30-day daily costs
    assert snapshot.cost_day_count == 30
    assert len(snapshot.daily_costs) == 30
