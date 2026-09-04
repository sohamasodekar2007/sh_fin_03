from __future__ import annotations

from datetime import datetime, timezone

from botocore.exceptions import ClientError

from packages.schemas.cloud_resource import EBSVolumeResourceRecord, EC2ResourceRecord
from packages.aws.session import AWSClientFactory


class EC2CollectionError(Exception):
    """Raised when EC2 inventory cannot be collected."""


class EBSCollectionError(Exception):
    """Raised when EBS volume inventory cannot be collected."""


def tags_to_dictionary(
    tags: list[dict] | None,
) -> dict[str, str]:
    result: dict[str, str] = {}

    for tag in tags or []:
        key = tag.get("Key")

        if not key:
            continue

        result[str(key)] = str(tag.get("Value", ""))

    return result


def find_tag(
    tags: dict[str, str],
    required_key: str,
) -> str | None:
    for key, value in tags.items():
        if key.lower() == required_key.lower():
            return value

    return None


def normalize_environment(
    tags: dict[str, str],
) -> str:
    raw_environment = find_tag(tags, "Environment")

    if not raw_environment:
        return "unknown"

    normalized = raw_environment.strip().lower()

    aliases = {
        "dev": "development",
        "development": "development",
        "stage": "staging",
        "stg": "staging",
        "staging": "staging",
        "prod": "production",
        "production": "production",
    }

    return aliases.get(normalized, "unknown")


def normalize_instance(
    instance: dict,
    region: str,
    collected_at: datetime,
) -> EC2ResourceRecord:
    tags = tags_to_dictionary(instance.get("Tags"))

    resource_id = instance["InstanceId"]

    name = find_tag(tags, "Name") or resource_id

    placement = instance.get("Placement") or {}
    state = instance.get("State") or {}
    environment = normalize_environment(tags)

    warnings: list[str] = []

    if not instance.get("Tags"):
        warnings.append("RESOURCE_HAS_NO_TAGS")

    if environment == "unknown":
        warnings.append("ENVIRONMENT_TAG_MISSING_OR_INVALID")

    return EC2ResourceRecord(
        region=region,
        availability_zone=placement.get("AvailabilityZone"),
        resource_id=resource_id,
        name=name,
        environment=environment,
        instance_type=instance.get(
            "InstanceType",
            "unknown",
        ),
        state=state.get("Name", "unknown"),
        launched_at=instance.get("LaunchTime"),
        collected_at=collected_at,
        private_ip=instance.get("PrivateIpAddress"),
        public_ip=instance.get("PublicIpAddress"),
        vpc_id=instance.get("VpcId"),
        subnet_id=instance.get("SubnetId"),
        tags=tags,
        warnings=warnings,
    )


class EC2Collector:
    def __init__(
        self,
        client_factory: AWSClientFactory,
        region: str,
    ):
        self.client_factory = client_factory
        self.region = region

    def collect(self) -> list[EC2ResourceRecord]:
        ec2 = self.client_factory.client(
            "ec2",
            region_name=self.region,
        )

        paginator = ec2.get_paginator(
            "describe_instances"
        )

        collected_at = datetime.now(timezone.utc)

        resources: list[EC2ResourceRecord] = []

        try:
            for page in paginator.paginate():
                reservations = page.get(
                    "Reservations",
                    [],
                )

                for reservation in reservations:
                    instances = reservation.get(
                        "Instances",
                        [],
                    )

                    for instance in instances:
                        resource = normalize_instance(
                            instance=instance,
                            region=self.region,
                            collected_at=collected_at,
                        )

                        resources.append(resource)

        except ClientError as error:
            error_code = error.response.get(
                "Error",
                {},
            ).get(
                "Code",
                "UNKNOWN_AWS_ERROR",
            )

            raise EC2CollectionError(
                f"EC2 collection failed: {error_code}"
            ) from error

        return resources


def normalize_volume(
    volume: dict,
    region: str,
    collected_at: datetime,
) -> EBSVolumeResourceRecord:
    tags = tags_to_dictionary(volume.get("Tags"))

    resource_id = volume["VolumeId"]
    name = find_tag(tags, "Name") or resource_id
    environment = normalize_environment(tags)
    state = str(volume.get("State", "unknown")).lower()

    size_gb = volume.get("Size", 0)
    volume_type = volume.get("VolumeType", "unknown")

    warnings: list[str] = []
    if not volume.get("Tags"):
        warnings.append("RESOURCE_HAS_NO_TAGS")
    if state == "available":
        # Mirrors mock_provider's convention — a "found" unattached volume,
        # not an error, but the signal the Analyzer's storage rule fires on.
        warnings.append("UNATTACHED_EBS_VOLUME")

    return EBSVolumeResourceRecord(
        region=region,
        availability_zone=volume.get("AvailabilityZone"),
        resource_id=resource_id,
        name=name,
        environment=environment,
        instance_type=f"{size_gb}GB-{volume_type}",
        state=state,
        launched_at=volume.get("CreateTime"),
        collected_at=collected_at,
        tags=tags,
        warnings=warnings,
    )


class EBSCollector:
    """Real EBS volume inventory — the resource type the Analyzer's
    unattached-storage rule (services/analyzer/service.py, keyed on FOCUS
    ServiceCategory == "Storage") looks for. Without this, that rule could
    only ever fire on mock data: EC2Collector alone never produces a
    resource_type == "ebs_volume" record."""

    def __init__(
        self,
        client_factory: AWSClientFactory,
        region: str,
    ):
        self.client_factory = client_factory
        self.region = region

    def collect(self) -> list[EBSVolumeResourceRecord]:
        ec2 = self.client_factory.client(
            "ec2",
            region_name=self.region,
        )

        paginator = ec2.get_paginator("describe_volumes")
        collected_at = datetime.now(timezone.utc)

        volumes: list[EBSVolumeResourceRecord] = []

        try:
            for page in paginator.paginate():
                for volume in page.get("Volumes", []):
                    volumes.append(
                        normalize_volume(
                            volume=volume,
                            region=self.region,
                            collected_at=collected_at,
                        )
                    )
        except ClientError as error:
            error_code = error.response.get("Error", {}).get(
                "Code", "UNKNOWN_AWS_ERROR"
            )
            raise EBSCollectionError(
                f"EBS collection failed: {error_code}"
            ) from error

        return volumes
