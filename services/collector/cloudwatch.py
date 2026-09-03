"""
CloudWatch metrics collector — real boto3 implementation.

Pulls CPUUtilization / NetworkIn+Out over a `days`-day window at 1-hour
resolution, matching the evidence window classify_idle() and
classify_over_provisioned() in services/analyzer/rules.py expect.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any


def _get_metric(session, region: str, instance_id: str, metric_name: str, stat: str, days: int) -> list[dict[str, Any]]:
    cw = session.client("cloudwatch", region_name=region)
    end = datetime.now(timezone.utc)
    start = end - timedelta(days=days)
    response = cw.get_metric_statistics(
        Namespace="AWS/EC2",
        MetricName=metric_name,
        Dimensions=[{"Name": "InstanceId", "Value": instance_id}],
        StartTime=start,
        EndTime=end,
        Period=3600,
        Statistics=[stat],
    )
    points = sorted(response.get("Datapoints", []), key=lambda p: p["Timestamp"])
    return [
        {"Timestamp": p["Timestamp"].isoformat(), stat.capitalize(): p[stat]}
        for p in points
    ]


def get_cpu_utilization(session, instance_id: str, region: str, days: int = 14) -> list[dict[str, Any]]:
    return _get_metric(session, region, instance_id, "CPUUtilization", "Average", days)


def get_network_utilization(session, instance_id: str, region: str, days: int = 14) -> list[dict[str, Any]]:
    net_in = _get_metric(session, region, instance_id, "NetworkIn", "Sum", days)
    net_out = _get_metric(session, region, instance_id, "NetworkOut", "Sum", days)
    by_ts: dict[str, float] = {}
    for point in net_in + net_out:
        by_ts[point["Timestamp"]] = by_ts.get(point["Timestamp"], 0.0) + point["Sum"]
    return [{"Timestamp": ts, "Sum": total} for ts, total in sorted(by_ts.items())]
