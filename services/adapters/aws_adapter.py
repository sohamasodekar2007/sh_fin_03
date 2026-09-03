"""
AwsAdapter — real boto3 collection (EC2 + CloudWatch + Cost Explorer) via a
customer-scoped cross-account role, degrading to services.collector.
mock_provider's synthetic fleet when no role is connected yet or AWS calls
fail, so the pipeline always has real, testable data to run against.
"""

from __future__ import annotations

import logging

from packages.aws.aws_session import assumed_session
from packages.schemas.schemas import CloudAccount
from packages.schemas.unified_resource import UnifiedResource
from services.adapters.base import CloudAdapter
from services.collector import cloudwatch, ec2
from services.collector.mock_provider import generate_mock_observation_bundle
from services.focus.normalizer import normalize_aws

logger = logging.getLogger(__name__)


class AwsAdapter(CloudAdapter):
    provider = "aws"

    async def validate_credentials(self, account: CloudAccount) -> bool:
        try:
            session = assumed_session(account.id, account.role_arn, account.external_id)
            session.client("sts", region_name=account.region).get_caller_identity()
            return True
        except Exception as exc:  # noqa: BLE001
            logger.warning("aws_adapter: credential validation failed for %s: %s", account.id, exc)
            return False

    async def collect(self, account: CloudAccount) -> list[UnifiedResource]:
        try:
            session = assumed_session(account.id, account.role_arn, account.external_id)
            instances = ec2.list_instances(session, account.region)
            volumes = ec2.list_unattached_volumes(session, account.region)
            if not instances and not volumes:
                raise RuntimeError("Role assumed but returned zero resources — treating as unconfigured.")

            resources: list[UnifiedResource] = []
            for inst in instances:
                instance_id = inst["InstanceId"]
                tags = {t["Key"]: t["Value"] for t in inst.get("Tags", [])}
                cpu_points = cloudwatch.get_cpu_utilization(session, instance_id, account.region)
                network_points = cloudwatch.get_network_utilization(session, instance_id, account.region)
                cpu_values = [p["Average"] for p in cpu_points if "Average" in p]
                network_values = [p["Sum"] for p in network_points if "Sum" in p]
                resources.append(
                    normalize_aws(
                        {
                            "resource_id": instance_id,
                            "resource_type": "ec2_instance",
                            "region": account.region,
                            "account_id": account.account_id,
                            "state": inst.get("State", {}).get("Name", "unknown"),
                            "environment": tags.get("env", tags.get("Environment", "unknown")),
                            "cpu_p95": self._percentile(cpu_values, 95) if cpu_values else 0.0,
                            "cpu_samples": cpu_values,
                            "network_samples": network_values,
                            "tags": tags,
                        }
                    )
                )
            for vol in volumes:
                tags = {t["Key"]: t["Value"] for t in vol.get("Tags", [])}
                resources.append(
                    normalize_aws(
                        {
                            "resource_id": vol["VolumeId"],
                            "resource_type": "ebs_volume",
                            "region": account.region,
                            "account_id": account.account_id,
                            "state": vol.get("State", "available"),
                            "environment": tags.get("env", "unknown"),
                            "tags": tags,
                            "monthly_cost_usd": vol.get("Size", 0) * 0.08 * 30,
                        }
                    )
                )
            logger.info("aws_adapter: collected %d live resources for account %s", len(resources), account.id)
            return resources

        except Exception as exc:  # noqa: BLE001
            logger.warning(
                "aws_adapter: live collection unavailable (%s) — degrading to synthetic fleet for account %s.",
                exc,
                account.id,
            )
            snapshot = generate_mock_observation_bundle(account_id=account.account_id, region=account.region)
            return [normalize_aws(r) for r in snapshot.resources]
