from __future__ import annotations

from datetime import datetime, timezone

from botocore.exceptions import ClientError

from packages.aws.session import AWSClientFactory
from packages.schemas.cloud_resource import DependencyContext, RDSInstanceResourceRecord
from services.collector.ec2_collector import normalize_environment, tags_to_dictionary
from services.governance.tags import has_missing_ownership


class RDSCollectionError(Exception):
    """Raised when RDS instance inventory cannot be collected."""


def normalize_db_instance(
    instance: dict,
    region: str,
    collected_at: datetime,
) -> RDSInstanceResourceRecord:
    tags = tags_to_dictionary(instance.get("TagList"))

    resource_id = instance["DBInstanceIdentifier"]
    environment = normalize_environment(tags)

    warnings: list[str] = []
    if not instance.get("TagList"):
        warnings.append("RESOURCE_HAS_NO_TAGS")
    if environment == "unknown":
        warnings.append("ENVIRONMENT_TAG_MISSING_OR_INVALID")
    if not instance.get("MultiAZ", False) and str(instance.get("DBInstanceStatus", "")).lower() == "available":
        warnings.append("SINGLE_AZ_NO_REDUNDANCY")

    return RDSInstanceResourceRecord(
        region=region,
        resource_id=resource_id,
        name=resource_id,
        environment=environment,
        instance_type=instance.get("DBInstanceClass", "unknown"),
        state=str(instance.get("DBInstanceStatus", "unknown")).lower(),
        launched_at=instance.get("InstanceCreateTime"),
        collected_at=collected_at,
        tags=tags,
        warnings=warnings,
        # multi_az/deletion_protection are already in this same
        # describe_db_instances response — no extra AWS call needed.
        dependency_context=DependencyContext(
            multi_az=instance.get("MultiAZ"),
            deletion_protection=instance.get("DeletionProtection"),
            missing_ownership=has_missing_ownership(tags),
        ),
    )


class RDSCollector:
    def __init__(self, client_factory: AWSClientFactory, region: str):
        self.client_factory = client_factory
        self.region = region

    def collect(self) -> list[RDSInstanceResourceRecord]:
        rds = self.client_factory.client("rds", region_name=self.region)
        paginator = rds.get_paginator("describe_db_instances")
        collected_at = datetime.now(timezone.utc)

        instances: list[RDSInstanceResourceRecord] = []
        try:
            for page in paginator.paginate():
                for instance in page.get("DBInstances", []):
                    instances.append(
                        normalize_db_instance(
                            instance=instance,
                            region=self.region,
                            collected_at=collected_at,
                        )
                    )
        except ClientError as error:
            error_code = error.response.get("Error", {}).get("Code", "UNKNOWN_AWS_ERROR")
            raise RDSCollectionError(f"RDS collection failed: {error_code}") from error

        return instances
