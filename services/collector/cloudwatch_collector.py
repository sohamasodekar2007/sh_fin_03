from datetime import datetime, timedelta, timezone
from typing import Any

from packages.schemas.cloud_metrics import EC2CpuMetric


class CloudWatchCollector:
    def __init__(self, cloudwatch_client: Any, region: str) -> None:
        self.cloudwatch_client = cloudwatch_client
        self.region = region

    def _get_datapoints(
        self,
        instance_id: str,
        metric_name: str,
        window_start: datetime,
        window_end: datetime,
        unit: str,
    ) -> list[dict[str, Any]]:
        response = self.cloudwatch_client.get_metric_statistics(
            Namespace="AWS/EC2",
            MetricName=metric_name,
            Dimensions=[{"Name": "InstanceId", "Value": instance_id}],
            StartTime=window_start,
            EndTime=window_end,
            Period=3600,
            Statistics=["Average", "Maximum"],
            Unit=unit,
        )
        return sorted(
            response.get("Datapoints", []),
            key=lambda point: point["Timestamp"],
        )

    def collect_cpu_metrics(
        self,
        instance_ids: list[str],
        hours: int = 24,
    ) -> list[EC2CpuMetric]:
        if hours < 1:
            raise ValueError("hours must be at least 1")

        window_end = datetime.now(timezone.utc)
        window_start = window_end - timedelta(hours=hours)

        collected_metrics: list[EC2CpuMetric] = []

        for instance_id in instance_ids:
            if not instance_id:
                continue

            datapoints = self._get_datapoints(
                instance_id, "CPUUtilization", window_start, window_end, "Percent"
            )

            average_values = [
                float(point["Average"])
                for point in datapoints
                if "Average" in point
            ]

            maximum_values = [
                float(point["Maximum"])
                for point in datapoints
                if "Maximum" in point
            ]

            # NetworkIn + NetworkOut are separate CloudWatch metrics; sum
            # each period's two totals into one "network activity" series,
            # then take the same average/maximum shape as CPU above.
            net_in = self._get_datapoints(
                instance_id, "NetworkIn", window_start, window_end, "Bytes"
            )
            net_out = self._get_datapoints(
                instance_id, "NetworkOut", window_start, window_end, "Bytes"
            )
            net_in_by_ts = {p["Timestamp"]: p for p in net_in}
            net_out_by_ts = {p["Timestamp"]: p for p in net_out}
            network_totals = [
                float(net_in_by_ts.get(ts, {}).get("Average", 0.0))
                + float(net_out_by_ts.get(ts, {}).get("Average", 0.0))
                for ts in set(net_in_by_ts) | set(net_out_by_ts)
            ]

            collected_metrics.append(
                EC2CpuMetric(
                    instance_id=instance_id,
                    region=self.region,
                    window_start=window_start,
                    window_end=window_end,
                    datapoint_count=len(datapoints),
                    average_cpu_percent=(
                        round(sum(average_values) / len(average_values), 4)
                        if average_values
                        else None
                    ),
                    maximum_cpu_percent=(
                        round(max(maximum_values), 4)
                        if maximum_values
                        else None
                    ),
                    average_network_bytes=(
                        round(sum(network_totals) / len(network_totals), 2)
                        if network_totals
                        else None
                    ),
                    maximum_network_bytes=(
                        round(max(network_totals), 2)
                        if network_totals
                        else None
                    ),
                    latest_datapoint_at=(
                        datapoints[-1]["Timestamp"] if datapoints else None
                    ),
                )
            )

        return collected_metrics
