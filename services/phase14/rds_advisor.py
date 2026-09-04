"""
RDS: recommend-only, always. Deliberately does not import
services/collector/rds_collector.py — that collector is pure inventory
(no CloudWatch, no idle detection) and lives in a different folder this
package must stay independent of; a few lines of boto3 here are cheaper
than a cross-folder dependency for a package meant to be deletable as a
single unit.

Every RDSRecommendation this produces states the AWS auto-restart
behavior explicitly: AWS automatically restarts a stopped RDS instance
after 7 days, so a proposal that goes silent on this would materially
mislead whoever approves it into thinking "stopped" means "stopped."
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Any

from botocore.exceptions import ClientError

from services.governance.tags import has_missing_ownership, is_excluded
from services.phase14.schemas import RDSRecommendation

logger = logging.getLogger(__name__)

# Longer and stricter than EC2's idle window (7 days) — a false positive
# on a database is much more expensive than on a compute instance.
EVIDENCE_WINDOW_DAYS = 21
IDLE_CONNECTIONS_THRESHOLD = 1.0
IDLE_CPU_THRESHOLD_PERCENT = 5.0


class RDSAdvisorError(Exception):
    """Raised when RDS recommendations cannot be collected at all."""


def _avg_metric(cloudwatch: Any, db_instance_id: str, metric_name: str, start: datetime, end: datetime) -> float | None:
    try:
        response = cloudwatch.get_metric_statistics(
            Namespace="AWS/RDS",
            MetricName=metric_name,
            Dimensions=[{"Name": "DBInstanceIdentifier", "Value": db_instance_id}],
            StartTime=start,
            EndTime=end,
            Period=86400,
            Statistics=["Average"],
        )
    except ClientError as error:
        logger.info("phase14.rds_advisor: metric %s failed for %s: %s", metric_name, db_instance_id, error)
        return None

    points = [p["Average"] for p in response.get("Datapoints", []) if "Average" in p]
    return sum(points) / len(points) if points else None


def _rationale(db_instance_id: str, connections: float | None, cpu: float | None) -> str:
    signal = []
    if connections is not None:
        signal.append(f"average {connections:.1f} connections/day")
    if cpu is not None:
        signal.append(f"average {cpu:.1f}% CPU")
    signal_text = ", ".join(signal) if signal else "no recent activity signal"
    return (
        f"{db_instance_id} shows {signal_text} over the trailing {EVIDENCE_WINDOW_DAYS} days — a stop "
        "candidate. This is a recommendation only; a human must approve it. AWS automatically restarts "
        "a stopped RDS instance after 7 days, so if approved, expect this instance to resume running "
        "and billing on its own after that window — stopping it is not a permanent action."
    )


class RDSAdvisor:
    def __init__(self, client_factory: Any, region: str):
        self.client_factory = client_factory
        self.region = region

    def collect_recommendations(self) -> list[RDSRecommendation]:
        rds = self.client_factory.client("rds", region_name=self.region)
        cloudwatch = self.client_factory.client("cloudwatch", region_name=self.region)

        try:
            paginator = rds.get_paginator("describe_db_instances")
            instances: list[dict[str, Any]] = []
            for page in paginator.paginate():
                instances.extend(page.get("DBInstances", []))
        except ClientError as error:
            error_code = error.response.get("Error", {}).get("Code", "UNKNOWN_AWS_ERROR")
            raise RDSAdvisorError(f"RDS recommendation collection failed: {error_code}") from error

        end = datetime.now(timezone.utc)
        start = end - timedelta(days=EVIDENCE_WINDOW_DAYS)

        recommendations: list[RDSRecommendation] = []
        for instance in instances:
            if str(instance.get("DBInstanceStatus", "")).lower() != "available":
                continue

            tags = {t["Key"]: t["Value"] for t in instance.get("TagList", [])}
            if is_excluded(tags):
                continue

            db_id = instance["DBInstanceIdentifier"]
            connections = _avg_metric(cloudwatch, db_id, "DatabaseConnections", start, end)
            cpu = _avg_metric(cloudwatch, db_id, "CPUUtilization", start, end)

            if connections is None and cpu is None:
                continue  # no signal at all — never guess idle from silence
            is_idle = (connections is not None and connections < IDLE_CONNECTIONS_THRESHOLD) or (
                cpu is not None and cpu < IDLE_CPU_THRESHOLD_PERCENT
            )
            if not is_idle:
                continue

            environment = str(tags.get("Environment", "unknown")).lower() or "unknown"

            rationale = _rationale(db_id, connections, cpu)
            if has_missing_ownership(tags):
                rationale += (
                    " No Owner or Environment tag is set on this resource — ownership is unclear, "
                    "which should factor into how quickly this gets approved."
                )

            recommendations.append(
                RDSRecommendation(
                    resource_id=db_id,
                    db_instance_class=instance.get("DBInstanceClass", "unknown"),
                    region=self.region,
                    environment=environment,
                    finding="idle_candidate",
                    confidence=0.7,
                    current_monthly_cost=None,  # no FOCUS join in this phase — never a guessed number
                    evidence={
                        "avg_connections": connections,
                        "avg_cpu_percent": cpu,
                        "window_days": EVIDENCE_WINDOW_DAYS,
                    },
                    rationale=rationale,
                )
            )

        return recommendations
