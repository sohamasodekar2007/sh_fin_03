from datetime import datetime, timezone
from unittest.mock import Mock

from services.collector.cloudwatch_collector import CloudWatchCollector


def test_collect_cpu_metrics_returns_normalized_result() -> None:
    client = Mock()

    client.get_metric_statistics.return_value = {
        "Datapoints": [
            {
                "Timestamp": datetime(2026, 7, 17, 10, tzinfo=timezone.utc),
                "Average": 3.0,
                "Maximum": 8.0,
                "Unit": "Percent",
            },
            {
                "Timestamp": datetime(2026, 7, 17, 11, tzinfo=timezone.utc),
                "Average": 7.0,
                "Maximum": 12.0,
                "Unit": "Percent",
            },
        ]
    }

    collector = CloudWatchCollector(
        cloudwatch_client=client,
        region="ap-south-1",
    )

    result = collector.collect_cpu_metrics(
        instance_ids=["i-0123456789abcdef0"],
        hours=24,
    )

    assert len(result) == 1
    assert result[0].instance_id == "i-0123456789abcdef0"
    assert result[0].datapoint_count == 2
    assert result[0].average_cpu_percent == 5.0
    assert result[0].maximum_cpu_percent == 12.0


def test_collect_cpu_metrics_handles_no_datapoints() -> None:
    client = Mock()
    client.get_metric_statistics.return_value = {"Datapoints": []}

    collector = CloudWatchCollector(
        cloudwatch_client=client,
        region="ap-south-1",
    )

    result = collector.collect_cpu_metrics(
        instance_ids=["i-empty"],
    )

    assert result[0].datapoint_count == 0
    assert result[0].average_cpu_percent is None
    assert result[0].maximum_cpu_percent is None
