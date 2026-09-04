from datetime import datetime, timezone
from decimal import Decimal
from unittest.mock import Mock, patch

from packages.schemas.cloud_metrics import (
    DailyCost,
    EC2CpuMetric,
)
from services.collector.collector_service import (
    AWSCollectorService,
)


@patch(
    "services.collector.collector_service."
    "CostExplorerCollector"
)
@patch(
    "services.collector.collector_service."
    "CloudWatchCollector"
)
@patch(
    "services.collector.collector_service.EBSCollector"
)
@patch(
    "services.collector.collector_service.EC2Collector"
)
def test_collect_snapshot_success(
    ec2_collector_class,
    ebs_collector_class,
    cloudwatch_collector_class,
    cost_collector_class,
) -> None:
    factory = Mock()
    factory.client.return_value = Mock()

    ec2_collector_class.return_value.collect.return_value = [
        {
            "resource_id": "i-example123",
            "resource_type": "ec2_instance",
            "state": "running",
        }
    ]

    ebs_collector_class.return_value.collect.return_value = [
        {
            "resource_id": "vol-example123",
            "resource_type": "ebs_volume",
            "state": "available",
        }
    ]

    cloudwatch_collector_class.return_value\
        .collect_cpu_metrics.return_value = [
            EC2CpuMetric(
                instance_id="i-example123",
                region="ap-south-1",
                window_start=datetime.now(timezone.utc),
                window_end=datetime.now(timezone.utc),
                datapoint_count=1,
                average_cpu_percent=2.5,
                maximum_cpu_percent=4.0,
            )
        ]

    cost_collector_class.return_value\
        .collect_daily_costs.return_value = [
            DailyCost(
                usage_date="2026-07-17",
                amount=Decimal("0.03"),
                currency="USD",
                estimated=True,
            )
        ]

    service = AWSCollectorService(
        client_factory=factory,
        region="ap-south-1",
        account_id="000000000000",
    )

    snapshot = service.collect_snapshot()

    assert snapshot.status == "success"
    assert snapshot.resource_count == 2
    assert snapshot.metric_count == 1
    assert snapshot.cost_day_count == 1
    assert snapshot.issues == []


@patch(
    "services.collector.collector_service."
    "CostExplorerCollector"
)
@patch(
    "services.collector.collector_service."
    "CloudWatchCollector"
)
@patch(
    "services.collector.collector_service.EBSCollector"
)
@patch(
    "services.collector.collector_service.EC2Collector"
)
def test_cost_results_are_cached(
    ec2_collector_class,
    ebs_collector_class,
    cloudwatch_collector_class,
    cost_collector_class,
) -> None:
    factory = Mock()
    factory.client.return_value = Mock()

    ec2_collector_class.return_value.collect.return_value = []
    ebs_collector_class.return_value.collect.return_value = []
    cloudwatch_collector_class.return_value\
        .collect_cpu_metrics.return_value = []
    cost_collector_class.return_value\
        .collect_daily_costs.return_value = []

    service = AWSCollectorService(
        client_factory=factory,
        region="ap-south-1",
        account_id="000000000000",
        cost_cache_hours=6,
    )

    service.collect_snapshot()
    service.collect_snapshot()

    assert (
        cost_collector_class.return_value
        .collect_daily_costs.call_count
        == 1
    )


@patch(
    "services.collector.collector_service."
    "CostExplorerCollector"
)
@patch(
    "services.collector.collector_service.EBSCollector"
)
@patch(
    "services.collector.collector_service.EC2Collector"
)
def test_snapshot_can_return_partial_status(
    ec2_collector_class,
    ebs_collector_class,
    cost_collector_class,
) -> None:
    factory = Mock()
    factory.client.return_value = Mock()

    ec2_collector_class.return_value.collect.side_effect = (
        RuntimeError("EC2 unavailable")
    )
    ebs_collector_class.return_value.collect.return_value = []

    cost_collector_class.return_value\
        .collect_daily_costs.return_value = []

    service = AWSCollectorService(
        client_factory=factory,
        region="ap-south-1",
        account_id="000000000000",
    )

    snapshot = service.collect_snapshot()

    assert snapshot.status == "partial"
    assert len(snapshot.issues) == 2
    assert snapshot.issues[0].source == "ec2"
    assert snapshot.issues[1].source == "cloudwatch"


@patch(
    "services.collector.collector_service."
    "CostExplorerCollector"
)
@patch(
    "services.collector.collector_service."
    "CloudWatchCollector"
)
@patch(
    "services.collector.collector_service.EBSCollector"
)
@patch(
    "services.collector.collector_service.EC2Collector"
)
def test_ebs_failure_is_isolated_from_ec2(
    ec2_collector_class,
    ebs_collector_class,
    cloudwatch_collector_class,
    cost_collector_class,
) -> None:
    """EBS collection is a separate describe_volumes call — it must not be
    skipped or fail the whole snapshot just because EC2 succeeded, and an
    EBS failure must not take EC2's resources down with it."""
    factory = Mock()
    factory.client.return_value = Mock()

    ec2_collector_class.return_value.collect.return_value = [
        {"resource_id": "i-example123", "resource_type": "ec2_instance", "state": "running"}
    ]
    ebs_collector_class.return_value.collect.side_effect = RuntimeError("EBS unavailable")
    cloudwatch_collector_class.return_value.collect_cpu_metrics.return_value = []
    cost_collector_class.return_value.collect_daily_costs.return_value = []

    service = AWSCollectorService(
        client_factory=factory,
        region="ap-south-1",
        account_id="000000000000",
    )

    snapshot = service.collect_snapshot()

    assert snapshot.status == "partial"
    assert snapshot.resource_count == 1
    assert any(issue.source == "ebs" for issue in snapshot.issues)
