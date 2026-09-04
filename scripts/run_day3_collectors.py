import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

BACKEND_ROOT = Path(__file__).resolve().parents[1]

if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from apps.api.config import get_settings
from services.collector.cloudwatch_collector import CloudWatchCollector
from services.collector.cost_collector import CostExplorerCollector
from packages.aws.session import AWSClientFactory


def list_instance_ids(ec2_client: Any) -> list[str]:
    instance_ids: list[str] = []
    paginator = ec2_client.get_paginator("describe_instances")

    for page in paginator.paginate():
        for reservation in page.get("Reservations", []):
            for instance in reservation.get("Instances", []):
                instance_id = instance.get("InstanceId")

                if instance_id:
                    instance_ids.append(instance_id)

    return instance_ids


def main() -> None:
    settings = get_settings()
    factory = AWSClientFactory(settings)

    ec2_client = factory.client(
        "ec2",
        region_name=settings.aws_region,
    )

    cloudwatch_client = factory.client(
        "cloudwatch",
        region_name=settings.aws_region,
    )

    cost_explorer_client = factory.client(
        "ce",
        region_name="us-east-1",
    )

    instance_ids = list_instance_ids(ec2_client)

    cloudwatch_collector = CloudWatchCollector(
        cloudwatch_client=cloudwatch_client,
        region=settings.aws_region,
    )

    cost_collector = CostExplorerCollector(
        cost_explorer_client=cost_explorer_client,
    )

    cpu_metrics = cloudwatch_collector.collect_cpu_metrics(
        instance_ids=instance_ids,
        hours=24,
    )

    daily_costs = cost_collector.collect_daily_costs(days=7)

    output = {
        "collected_at": datetime.now(timezone.utc).isoformat(),
        "region": settings.aws_region,
        "instance_count": len(instance_ids),
        "cpu_metrics": [
            metric.model_dump(mode="json")
            for metric in cpu_metrics
        ],
        "daily_costs": [
            cost.model_dump(mode="json")
            for cost in daily_costs
        ],
    }

    print(json.dumps(output, indent=2))


if __name__ == "__main__":
    main()
