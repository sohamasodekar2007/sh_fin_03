from __future__ import annotations

import logging
from datetime import datetime, timezone

from botocore.exceptions import ClientError

from packages.schemas.cloud_resource import (
    DependencyContext,
    EBSVolumeResourceRecord,
    EC2ResourceRecord,
    SecurityGroupResourceRecord,
    VPCResourceRecord,
)
from packages.aws.session import AWSClientFactory
from services.governance.tags import has_missing_ownership

logger = logging.getLogger(__name__)


class EC2CollectionError(Exception):
    """Raised when EC2 inventory cannot be collected."""


class EBSCollectionError(Exception):
    """Raised when EBS volume inventory cannot be collected."""


class VPCCollectionError(Exception):
    """Raised when VPC inventory cannot be collected."""


class SecurityGroupCollectionError(Exception):
    """Raised when security group inventory cannot be collected."""


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


def _chunked(items: list[str], size: int) -> list[list[str]]:
    return [items[i : i + size] for i in range(0, len(items), size)]


def attach_ec2_dependency_context(
    records: list[EC2ResourceRecord],
    autoscaling_client,
    elbv2_client,
    ec2_client,
) -> None:
    """Phase 15 — populates each record's dependency_context in place, once
    per collection cycle, instead of Phase 14's original design (the same
    ASG/LB/termination-protection facts, re-fetched live on every Decision
    Agent trigger). Every call here is a free Describe/List call, batched
    wherever the AWS API allows it: one describe_auto_scaling_instances per
    50-instance chunk (not one per instance), one describe_target_groups +
    one describe_target_health per group (not one per instance x group).
    Termination protection has no batch API — same per-instance cost as
    before, just moved earlier. Never raises past this function: any
    ClientError degrades that lookup to its safe default and is logged,
    never breaks the base EC2 inventory this runs after."""
    if not records:
        return

    by_id = {r.resource_id: r for r in records}
    instance_ids = list(by_id.keys())

    asg_name_by_instance: dict[str, str] = {}
    try:
        for chunk in _chunked(instance_ids, 50):
            response = autoscaling_client.describe_auto_scaling_instances(InstanceIds=chunk)
            for entry in response.get("AutoScalingInstances", []):
                asg_name_by_instance[entry["InstanceId"]] = entry["AutoScalingGroupName"]
    except ClientError as error:
        logger.info("ec2_collector: ASG membership lookup failed, dependency_context degraded: %s", error)

    asg_capacity: dict[str, tuple[int | None, int | None]] = {}
    distinct_asg_names = sorted(set(asg_name_by_instance.values()))
    if distinct_asg_names:
        try:
            for chunk in _chunked(distinct_asg_names, 100):
                response = autoscaling_client.describe_auto_scaling_groups(AutoScalingGroupNames=chunk)
                for group in response.get("AutoScalingGroups", []):
                    asg_capacity[group["AutoScalingGroupName"]] = (
                        group.get("DesiredCapacity"),
                        group.get("MinSize"),
                    )
        except ClientError as error:
            logger.info("ec2_collector: ASG capacity lookup failed, dependency_context degraded: %s", error)

    lb_targets_by_instance: dict[str, list[str]] = {}
    try:
        groups = elbv2_client.describe_target_groups().get("TargetGroups", [])
        for group in groups:
            try:
                health = elbv2_client.describe_target_health(TargetGroupArn=group["TargetGroupArn"])
            except ClientError as error:
                logger.info(
                    "ec2_collector: target-health lookup failed for %s: %s", group.get("TargetGroupArn"), error
                )
                continue
            for desc in health.get("TargetHealthDescriptions", []):
                target_id = desc.get("Target", {}).get("Id")
                if target_id in by_id:
                    lb_targets_by_instance.setdefault(target_id, []).append(group["TargetGroupArn"])
    except ClientError as error:
        logger.info("ec2_collector: target group listing failed, dependency_context degraded: %s", error)

    for instance_id, record in by_id.items():
        try:
            attr = ec2_client.describe_instance_attribute(InstanceId=instance_id, Attribute="disableApiTermination")
            termination_protected = bool(attr.get("DisableApiTermination", {}).get("Value", False))
        except ClientError as error:
            # Fail-safe direction matches Phase 14's ec2_safety.py precedent:
            # "can't confirm" is treated as protected, never as safe-to-stop.
            logger.info(
                "ec2_collector: termination-protection lookup failed for %s, assuming protected: %s",
                instance_id, error,
            )
            termination_protected = True

        asg_name = asg_name_by_instance.get(instance_id)
        desired, min_size = asg_capacity.get(asg_name, (None, None)) if asg_name else (None, None)

        record.dependency_context = DependencyContext(
            in_autoscaling_group=asg_name,
            asg_desired_capacity=desired,
            asg_min_size=min_size,
            load_balancer_targets=lb_targets_by_instance.get(instance_id, []),
            termination_protected=termination_protected,
            missing_ownership=has_missing_ownership(record.tags),
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

        try:
            autoscaling = self.client_factory.client("autoscaling", region_name=self.region)
            elbv2 = self.client_factory.client("elbv2", region_name=self.region)
            attach_ec2_dependency_context(resources, autoscaling, elbv2, ec2)
        except Exception as error:  # noqa: BLE001 - dependency context is best-effort, never blocks inventory
            logger.info("ec2_collector: dependency_context attachment failed entirely, records keep safe defaults: %s", error)

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


def normalize_vpc(
    vpc: dict,
    region: str,
    collected_at: datetime,
) -> VPCResourceRecord:
    tags = tags_to_dictionary(vpc.get("Tags"))

    resource_id = vpc["VpcId"]
    name = find_tag(tags, "Name") or resource_id
    environment = normalize_environment(tags)

    warnings: list[str] = []
    if not vpc.get("Tags"):
        warnings.append("RESOURCE_HAS_NO_TAGS")

    return VPCResourceRecord(
        region=region,
        resource_id=resource_id,
        name=name,
        environment=environment,
        instance_type=str(vpc.get("CidrBlock", "unknown")),
        state=str(vpc.get("State", "unknown")).lower(),
        collected_at=collected_at,
        tags=tags,
        warnings=warnings,
    )


class VPCCollector:
    """Real VPC inventory — not itself a billable resource (a VPC has no
    hourly rate), but real network-topology context for the Resources page.
    Same client as EC2Collector, so it lives in this file rather than a
    dedicated one."""

    def __init__(
        self,
        client_factory: AWSClientFactory,
        region: str,
    ):
        self.client_factory = client_factory
        self.region = region

    def collect(self) -> list[VPCResourceRecord]:
        ec2 = self.client_factory.client(
            "ec2",
            region_name=self.region,
        )

        paginator = ec2.get_paginator("describe_vpcs")
        collected_at = datetime.now(timezone.utc)

        vpcs: list[VPCResourceRecord] = []

        try:
            for page in paginator.paginate():
                for vpc in page.get("Vpcs", []):
                    vpcs.append(
                        normalize_vpc(
                            vpc=vpc,
                            region=self.region,
                            collected_at=collected_at,
                        )
                    )
        except ClientError as error:
            error_code = error.response.get("Error", {}).get(
                "Code", "UNKNOWN_AWS_ERROR"
            )
            raise VPCCollectionError(
                f"VPC collection failed: {error_code}"
            ) from error

        return vpcs


def _security_group_ingress_rules(group: dict) -> list[dict]:
    rules: list[dict] = []
    for permission in group.get("IpPermissions", []):
        protocol = str(permission.get("IpProtocol", "all"))
        from_port = permission.get("FromPort")
        to_port = permission.get("ToPort")
        cidrs = [entry.get("CidrIp") for entry in permission.get("IpRanges", []) if entry.get("CidrIp")]
        cidrs.extend(entry.get("CidrIpv6") for entry in permission.get("Ipv6Ranges", []) if entry.get("CidrIpv6"))
        for cidr in cidrs:
            rules.append(
                {
                    "protocol": protocol,
                    "from_port": from_port,
                    "to_port": to_port,
                    "cidr": cidr,
                }
            )
    return rules


def normalize_security_group(
    group: dict,
    region: str,
    collected_at: datetime,
) -> SecurityGroupResourceRecord:
    tags = tags_to_dictionary(group.get("Tags"))
    resource_id = group["GroupId"]
    name = find_tag(tags, "Name") or group.get("GroupName") or resource_id
    environment = normalize_environment(tags)
    ingress_rules = _security_group_ingress_rules(group)

    warnings: list[str] = []
    if not tags:
        warnings.append("RESOURCE_HAS_NO_TAGS")
    if any(rule.get("cidr") in {"0.0.0.0/0", "::/0"} for rule in ingress_rules):
        warnings.append("HAS_INTERNET_INGRESS")

    return SecurityGroupResourceRecord(
        region=region,
        resource_id=resource_id,
        name=name,
        environment=environment,
        instance_type=group.get("GroupName") or "security_group",
        state="active",
        collected_at=collected_at,
        tags=tags,
        warnings=warnings,
        vpc_id=group.get("VpcId"),
        ingress_rules=ingress_rules,
        dependency_context=DependencyContext(missing_ownership=has_missing_ownership(tags)),
    )


class SecurityGroupCollector:
    def __init__(
        self,
        client_factory: AWSClientFactory,
        region: str,
    ):
        self.client_factory = client_factory
        self.region = region

    def collect(self) -> list[SecurityGroupResourceRecord]:
        ec2 = self.client_factory.client("ec2", region_name=self.region)
        paginator = ec2.get_paginator("describe_security_groups")
        collected_at = datetime.now(timezone.utc)

        groups: list[SecurityGroupResourceRecord] = []
        try:
            for page in paginator.paginate():
                for group in page.get("SecurityGroups", []):
                    groups.append(normalize_security_group(group, self.region, collected_at))
        except ClientError as error:
            error_code = error.response.get("Error", {}).get("Code", "UNKNOWN_AWS_ERROR")
            raise SecurityGroupCollectionError(f"Security group collection failed: {error_code}") from error

        return groups
