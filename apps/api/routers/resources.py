import asyncio
import logging
import re
from typing import Any

from botocore.exceptions import ClientError, ProfileNotFound
from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.encoders import jsonable_encoder

from apps.api.config import get_settings
from apps.api.db import get_db, mongo_available
from apps.api.dependencies import CurrentUser
from apps.api.mock_data import RESOURCES
from packages.aws.session import AWSClientFactory
from packages.schemas.schemas import ActionProposal, Resource
from pydantic import BaseModel
from services.collector.collector_service import AWSCollectorService
from services.analyzer.service import analyze_observation
from services.decision.service import build_proposals
from services.executor.actions import ExecutionRefused, assumed_write_session
from services.focus import repository as focus_repository
from services.focus.metrics import ResourceMetric, get_resource_metric

router = APIRouter(prefix="/v1/resources", tags=["resources"])
logger = logging.getLogger(__name__)


def _tags_to_dict(tags: list[dict[str, Any]] | None) -> dict[str, str]:
    return {str(tag.get("Key")): str(tag.get("Value", "")) for tag in tags or [] if tag.get("Key")}


def _dashboard_environment(raw: Any) -> str:
    normalized = str(raw or "").strip().lower()
    if normalized in {"prod", "production"}:
        return "prod"
    if normalized in {"stage", "stg", "staging"}:
        return "staging"
    return "dev"


def _status_from_state(state: str | None) -> str:
    return "Healthy" if state == "running" else "At-risk"


def _last_live_aws_resources(region: str) -> list[Resource]:
    settings = get_settings()
    rows = [
        ("i-0a34c54ac18e0eb62", "CloudCare-Test_server", "dev", "stopped"),
        ("i-0a243d0480eab6ce6", "CloudCare-Test_server2", "dev", "stopped"),
        ("i-0ef82f9beda9ce805", "CloudCare_Final", "dev", "stopped"),
        ("i-0cb4a68a191137e7d", "Cloud_Instance", "dev", "running"),
        ("i-027be67f93b8d080d", "cc-test-asg-idle", "dev", "running"),
    ]
    return [
        Resource(
            id=instance_id,
            type="t3.micro",
            region=region,
            cpu_p95=0.0,
            status=_status_from_state(state),
            monthly_cost_usd=None,
            cost_source="no_focus_row",
            focus_version=settings.focus_version,
            focus_source="last_live_snapshot",
            focus_row_count=0,
            resource_type="ec2_instance",
            instance_type="t3.micro",
            vcpu=2,
            memory_gib=1.0,
            provider="aws",
            state=state,
            tags={"Name": name, "Environment": environment},
            environment=environment,
        )
        for instance_id, name, environment, state in rows
    ]


def _live_aws_resources(region: str) -> list[Resource]:
    settings = get_settings()
    try:
        snapshot = AWSCollectorService(
            client_factory=AWSClientFactory(settings),
            region=region,
            account_id=settings.aws_account_id or "demo-account",
        ).collect_snapshot()
        resources = []
        for raw in snapshot.model_dump(mode="json").get("resources") or []:
            resource_id = raw.get("resource_id") or raw.get("instance_id") or raw.get("id")
            if not resource_id:
                continue
            state = raw.get("state")
            tags = raw.get("tags") or {}
            instance_type = raw.get("instance_type") or raw.get("type") or raw.get("resource_type") or "aws"
            instance_specs = _EC2_INSTANCE_SPECS.get(str(instance_type), {}) if raw.get("resource_type") == "ec2_instance" else {}
            resources.append(
                Resource(
                    id=resource_id,
                    type=instance_type,
                    region=raw.get("region") or region,
                    cpu_p95=0.0,
                    status=_status_from_state(state),
                    monthly_cost_usd=None,
                    cost_source="no_focus_row",
                    focus_version=settings.focus_version,
                    focus_source="live",
                    focus_row_count=0,
                    resource_type=raw.get("resource_type"),
                    instance_type=str(instance_type) if raw.get("resource_type") == "ec2_instance" else None,
                    vcpu=instance_specs.get("vcpu"),
                    memory_gib=instance_specs.get("memory_gib"),
                    provider="aws",
                    state=state,
                    tags=tags,
                    environment=_dashboard_environment(raw.get("environment") or tags.get("Environment")),
                )
            )
        resources.sort(key=lambda item: (item.state != "running", item.tags.get("Name", ""), item.id))
        return resources
    except ProfileNotFound:
        logger.warning("resources: configured AWS profile not found; using last live AWS fallback")
        return _last_live_aws_resources(region)
    except Exception:
        logger.exception("resources: full AWS fallback failed; using EC2-only fallback")

    try:
        session = assumed_write_session("resources-list-ec2")
        ec2 = session.client("ec2", region_name=region)
        resp = ec2.describe_instances()
    except ProfileNotFound:
        logger.warning("resources: EC2 fallback AWS profile not found; using last live AWS fallback")
        return _last_live_aws_resources(region)

    resources: list[Resource] = []
    for reservation in resp.get("Reservations", []):
        for instance in reservation.get("Instances", []):
            tags = _tags_to_dict(instance.get("Tags"))
            state = instance.get("State", {}).get("Name", "unknown")
            instance_type = instance.get("InstanceType", "ec2")
            instance_specs = _EC2_INSTANCE_SPECS.get(str(instance_type), {})
            resources.append(
                Resource(
                    id=instance["InstanceId"],
                    type=instance_type,
                    region=region,
                    cpu_p95=0.0,
                    status=_status_from_state(state),
                    monthly_cost_usd=None,
                    cost_source="no_focus_row",
                    focus_version=settings.focus_version,
                    focus_source="live",
                    focus_row_count=0,
                    resource_type="ec2_instance",
                    instance_type=str(instance_type),
                    vcpu=instance_specs.get("vcpu"),
                    memory_gib=instance_specs.get("memory_gib"),
                    provider="aws",
                    state=state,
                    tags=tags,
                    environment=_dashboard_environment(tags.get("Environment")),
                )
            )

    resources.sort(key=lambda item: (item.state != "running", item.tags.get("Name", ""), item.id))
    return resources


def _live_aws_resource_by_id(resource_id: str, region: str, resource_type: str | None = None) -> Resource | None:
    settings = get_settings()
    factory = AWSClientFactory(settings)
    collected_focus = settings.focus_version

    try:
        if resource_type == "ec2_instance" or resource_id.startswith("i-"):
            ec2 = factory.client("ec2", region_name=region)
            response = ec2.describe_instances(InstanceIds=[resource_id])
            instance = next(
                (
                    item
                    for reservation in response.get("Reservations", [])
                    for item in reservation.get("Instances", [])
                    if item.get("InstanceId") == resource_id
                ),
                None,
            )
            if not instance:
                return None
            tags = _tags_to_dict(instance.get("Tags"))
            state = instance.get("State", {}).get("Name", "unknown")
            instance_type = instance.get("InstanceType", "ec2")
            instance_specs = _EC2_INSTANCE_SPECS.get(str(instance_type), {})
            return Resource(
                id=resource_id,
                type=instance_type,
                region=region,
                cpu_p95=0.0,
                status=_status_from_state(state),
                monthly_cost_usd=None,
                cost_source="no_focus_row",
                focus_version=collected_focus,
                focus_source="live",
                focus_row_count=0,
                resource_type="ec2_instance",
                instance_type=str(instance_type),
                vcpu=instance_specs.get("vcpu"),
                memory_gib=instance_specs.get("memory_gib"),
                provider="aws",
                state=state,
                tags=tags,
                environment=_dashboard_environment(tags.get("Environment")),
            )
        if resource_type == "ebs_volume" or resource_id.startswith("vol-"):
            ec2 = factory.client("ec2", region_name=region)
            response = ec2.describe_volumes(VolumeIds=[resource_id])
            volume = next((item for item in response.get("Volumes", []) if item.get("VolumeId") == resource_id), None)
            if not volume:
                return None
            tags = _tags_to_dict(volume.get("Tags"))
            state = str(volume.get("State", "unknown")).lower()
            return Resource(
                id=resource_id,
                type=f"{volume.get('Size', 0)}GB-{volume.get('VolumeType', 'ebs')}",
                region=region,
                cpu_p95=0.0,
                status="At-risk" if state == "available" else "Healthy",
                monthly_cost_usd=None,
                cost_source="no_focus_row",
                focus_version=collected_focus,
                focus_source="live",
                focus_row_count=0,
                resource_type="ebs_volume",
                provider="aws",
                state=state,
                tags=tags,
                environment=_dashboard_environment(tags.get("Environment")),
            )
        if resource_type == "vpc" or resource_id.startswith("vpc-"):
            ec2 = factory.client("ec2", region_name=region)
            response = ec2.describe_vpcs(VpcIds=[resource_id])
            vpc = next((item for item in response.get("Vpcs", []) if item.get("VpcId") == resource_id), None)
            if not vpc:
                return None
            tags = _tags_to_dict(vpc.get("Tags"))
            return Resource(
                id=resource_id,
                type="vpc",
                region=region,
                cpu_p95=0.0,
                status="Healthy",
                monthly_cost_usd=None,
                cost_source="no_focus_row",
                focus_version=collected_focus,
                focus_source="live",
                focus_row_count=0,
                resource_type="vpc",
                provider="aws",
                state=vpc.get("State"),
                tags=tags,
                environment=_dashboard_environment(tags.get("Environment")),
            )
        if resource_type == "security_group" or resource_id.startswith("sg-"):
            ec2 = factory.client("ec2", region_name=region)
            response = ec2.describe_security_groups(GroupIds=[resource_id])
            group = next((item for item in response.get("SecurityGroups", []) if item.get("GroupId") == resource_id), None)
            if not group:
                return None
            tags = _tags_to_dict(group.get("Tags"))
            return Resource(
                id=resource_id,
                type="security-group",
                region=region,
                cpu_p95=0.0,
                status="Healthy",
                monthly_cost_usd=None,
                cost_source="no_focus_row",
                focus_version=collected_focus,
                focus_source="live",
                focus_row_count=0,
                resource_type="security_group",
                provider="aws",
                state="active",
                tags=tags,
                environment=_dashboard_environment(tags.get("Environment")),
            )
        if resource_type == "rds_instance":
            rds = factory.client("rds", region_name=region)
            response = rds.describe_db_instances(DBInstanceIdentifier=resource_id)
            instance = next(iter(response.get("DBInstances", [])), None)
            if not instance:
                return None
            tags = _tags_to_dict(instance.get("TagList"))
            return Resource(
                id=resource_id,
                type=instance.get("DBInstanceClass", "rds"),
                region=region,
                cpu_p95=0.0,
                status="Healthy" if instance.get("DBInstanceStatus") == "available" else "At-risk",
                monthly_cost_usd=None,
                cost_source="no_focus_row",
                focus_version=collected_focus,
                focus_source="live",
                focus_row_count=0,
                resource_type="rds_instance",
                provider="aws",
                state=str(instance.get("DBInstanceStatus", "unknown")).lower(),
                tags=tags,
                environment=_dashboard_environment(tags.get("Environment")),
            )
        if resource_type == "lambda_function":
            lambda_client = factory.client("lambda", region_name=region)
            response = lambda_client.get_function(FunctionName=resource_id)
            config = response.get("Configuration", {})
            tags = response.get("Tags") or {}
            return Resource(
                id=resource_id,
                type=config.get("Runtime") or "lambda",
                region=region,
                cpu_p95=0.0,
                status="Healthy",
                monthly_cost_usd=None,
                cost_source="no_focus_row",
                focus_version=collected_focus,
                focus_source="live",
                focus_row_count=0,
                resource_type="lambda_function",
                provider="aws",
                state=config.get("State") or "active",
                tags=tags,
                environment=_dashboard_environment(tags.get("Environment")),
            )
        if resource_type == "dynamodb_table":
            dynamodb = factory.client("dynamodb", region_name=region)
            response = dynamodb.describe_table(TableName=resource_id)
            table = response.get("Table", {})
            return Resource(
                id=resource_id,
                type=table.get("BillingModeSummary", {}).get("BillingMode") or "dynamodb",
                region=region,
                cpu_p95=0.0,
                status="Healthy" if table.get("TableStatus") == "ACTIVE" else "At-risk",
                monthly_cost_usd=None,
                cost_source="no_focus_row",
                focus_version=collected_focus,
                focus_source="live",
                focus_row_count=0,
                resource_type="dynamodb_table",
                provider="aws",
                state=table.get("TableStatus"),
                tags={},
                environment="dev",
            )
        if resource_type == "s3_bucket":
            s3 = factory.client("s3", region_name="us-east-1")
            location = s3.get_bucket_location(Bucket=resource_id)
            try:
                tags = _tags_to_dict(s3.get_bucket_tagging(Bucket=resource_id).get("TagSet"))
            except Exception:
                tags = {}
            return Resource(
                id=resource_id,
                type="bucket",
                region=location.get("LocationConstraint") or "us-east-1",
                cpu_p95=0.0,
                status="Healthy",
                monthly_cost_usd=None,
                cost_source="no_focus_row",
                focus_version=collected_focus,
                focus_source="live",
                focus_row_count=0,
                resource_type="s3_bucket",
                provider="aws",
                state="active",
                tags=tags,
                environment=_dashboard_environment(tags.get("Environment")),
            )
    except Exception:
        logger.exception("resources: direct live lookup failed for %s", resource_id)

    return None


async def _resources_collection():
    """Returns the `resources` Mongo collection, auto-seeding it from
    mock_data.py the first time it's empty so the demo/dashboard never
    shows a blank screen while real AWS collection (Soham's track) is
    still being wired in."""
    db = get_db()
    if await db.resources.count_documents({}) == 0:
        await db.resources.insert_many([r.model_dump() for r in RESOURCES])
    return db.resources


class ResourceCostPoint(BaseModel):
    date: str
    billed_cost: float


class ResourceChargeBreakdownItem(BaseModel):
    charge_description: str
    charge_category: str
    billed_cost: float
    row_count: int


class ResourceDetail(BaseModel):
    resource: Resource
    metric: ResourceMetric | None = None
    cost_trend: list[ResourceCostPoint]
    charge_breakdown: list[ResourceChargeBreakdownItem]
    focus_dataset_id: str | None = None
    focus_row_count: int = 0
    related_proposals: list[ActionProposal] = []
    raw_resource: dict[str, Any] = {}
    aws_live_details: dict[str, Any] = {}
    aws_live_errors: dict[str, str] = {}


class TagSavingsGroup(BaseModel):
    tag_value: str
    instances: int
    monthly_savings: float


class TagSavingsInstance(BaseModel):
    instance_id: str
    name: str
    tag_value: str
    instance_type: str
    vcpu: int | None = None
    memory_gib: float | None = None
    state: str | None = None
    actions: list[str]
    risk: str
    monthly_savings: float


class TagSavingsResponse(BaseModel):
    status: str
    provider: str
    account_id: str
    region: str
    tag_key: str
    available_tag_keys: list[str]
    resources: int
    findings: int
    proposals: int
    monthly_savings: float
    groups: list[TagSavingsGroup]
    instances: list[TagSavingsInstance]
    error: str | None = None


def _case_insensitive_tag_value(tags: dict[str, Any], tag_key: str) -> str:
    for key, value in (tags or {}).items():
        if str(key).lower() == tag_key.lower():
            return str(value) if value not in (None, "") else "untagged"
    return "untagged"


def _proposal_instance_id(proposal: dict[str, Any]) -> str | None:
    params = proposal.get("parameters") or {}
    instance_id = params.get("instance_id") or proposal.get("resource_id")
    if instance_id:
        return str(instance_id)
    resource_arn = str(proposal.get("resource_arn") or "")
    if ":instance/" in resource_arn:
        return resource_arn.rsplit("/", 1)[-1]
    return None


def _highest_risk(current: str, next_risk: str) -> str:
    weights = {"low": 1, "medium": 2, "high": 3, "critical": 4}
    return next_risk if weights.get(next_risk, 0) > weights.get(current, 0) else current


_EC2_INSTANCE_SPECS: dict[str, dict[str, float | int]] = {
    "t3.micro": {"vcpu": 2, "memory_gib": 1.0},
}


def _tag_savings_from_snapshot(snapshot_data: dict[str, Any], tag_key: str) -> TagSavingsResponse:
    findings = analyze_observation(snapshot_data)
    proposals = build_proposals(snapshot_data, findings)
    by_instance: dict[str, dict[str, Any]] = {}
    resources_by_id = {
        str(resource.get("instance_id") or resource.get("resource_id") or resource.get("id")): resource
        for resource in snapshot_data.get("resources") or []
        if resource.get("instance_id") or resource.get("resource_id") or resource.get("id")
    }
    available_tag_keys = sorted(
        {
            str(key)
            for resource in snapshot_data.get("resources") or []
            for key in (resource.get("tags") or {}).keys()
            if key
        },
        key=str.lower,
    )

    for proposal in proposals:
        instance_id = _proposal_instance_id(proposal)
        savings = float(proposal.get("expected_monthly_savings") or 0)
        if not instance_id or savings <= 0:
            continue
        resource_type = proposal.get("resource_type")
        if resource_type and resource_type != "ec2_instance":
            continue

        resource = resources_by_id.get(instance_id, {})
        instance_type = str(resource.get("instance_type") or resource.get("type") or "unknown")
        instance_specs = _EC2_INSTANCE_SPECS.get(instance_type, {})
        tag_value = _case_insensitive_tag_value(proposal.get("tags") or {}, tag_key)
        key = f"{instance_id}|{tag_value}"
        row = by_instance.setdefault(
            key,
            {
                "instance_id": instance_id,
                "name": proposal.get("resource_name") or instance_id,
                "tag_value": tag_value,
                "instance_type": instance_type,
                "vcpu": instance_specs.get("vcpu"),
                "memory_gib": instance_specs.get("memory_gib"),
                "state": resource.get("state"),
                "actions": set(),
                "risk": proposal.get("risk_level", "high"),
                "monthly_savings": 0.0,
            },
        )
        row["actions"].add(proposal.get("action_type"))
        row["risk"] = _highest_risk(row["risk"], proposal.get("risk_level", "high"))
        row["monthly_savings"] += savings

    instances = [
        TagSavingsInstance(
            instance_id=row["instance_id"],
            name=row["name"],
            tag_value=row["tag_value"],
            instance_type=row["instance_type"],
            vcpu=row["vcpu"],
            memory_gib=row["memory_gib"],
            state=row["state"],
            actions=sorted(action for action in row["actions"] if action),
            risk=row["risk"],
            monthly_savings=round(row["monthly_savings"], 2),
        )
        for row in by_instance.values()
    ]
    instances.sort(key=lambda item: item.monthly_savings, reverse=True)

    groups_by_value: dict[str, dict[str, Any]] = {}
    for instance in instances:
        group = groups_by_value.setdefault(instance.tag_value, {"instances": 0, "monthly_savings": 0.0})
        group["instances"] += 1
        group["monthly_savings"] += instance.monthly_savings

    groups = [
        TagSavingsGroup(
            tag_value=tag_value,
            instances=group["instances"],
            monthly_savings=round(group["monthly_savings"], 2),
        )
        for tag_value, group in groups_by_value.items()
    ]
    groups.sort(key=lambda item: item.monthly_savings, reverse=True)

    return TagSavingsResponse(
        status="success",
        provider="aws",
        account_id=str(snapshot_data.get("account_id") or get_settings().aws_account_id or "demo-account"),
        region=str(snapshot_data.get("region") or get_settings().aws_region),
        tag_key=tag_key,
        available_tag_keys=available_tag_keys or [tag_key],
        resources=int(snapshot_data.get("resource_count") or len(snapshot_data.get("resources") or [])),
        findings=len(findings),
        proposals=len(proposals),
        monthly_savings=round(sum(instance.monthly_savings for instance in instances), 2),
        groups=groups,
        instances=instances,
    )


def _build_cost_trend_and_breakdown(
    records: list[Any], resource_id: str
) -> tuple[list[ResourceCostPoint], list[ResourceChargeBreakdownItem]]:
    """Pure — no Mongo/FastAPI involved, so this is unit-testable directly
    (see tests/unit/test_resource_detail.py). `records` is
    FocusDataset.records; filtered to this resource_id, grouped into a
    chronological daily-cost trend and a charge-description breakdown
    sorted by cost descending, capped at 15 rows so a resource with
    hundreds of distinct charge descriptions doesn't blow up the payload."""
    matching = [row for row in records if row.ResourceId == resource_id]

    daily_totals: dict[str, float] = {}
    breakdown_totals: dict[tuple[str, str], dict[str, Any]] = {}
    for row in matching:
        day = row.ChargePeriodStart.date().isoformat()
        daily_totals[day] = daily_totals.get(day, 0.0) + float(row.BilledCost)
        key = (row.ChargeDescription, row.ChargeCategory)
        bucket = breakdown_totals.setdefault(key, {"cost": 0.0, "count": 0})
        bucket["cost"] += float(row.BilledCost)
        bucket["count"] += 1

    cost_trend = [ResourceCostPoint(date=day, billed_cost=round(cost, 4)) for day, cost in sorted(daily_totals.items())]
    charge_breakdown = sorted(
        (
            ResourceChargeBreakdownItem(
                charge_description=description,
                charge_category=category,
                billed_cost=round(bucket["cost"], 4),
                row_count=bucket["count"],
            )
            for (description, category), bucket in breakdown_totals.items()
        ),
        key=lambda item: item.billed_cost,
        reverse=True,
    )[:15]
    return cost_trend, charge_breakdown


async def _find_resource(current_user: CurrentUser, resource_id: str, resource_type: str | None = None) -> Resource | None:
    """Same two-tier lookup as list_resources: Mongo first, live AWS
    fallback second — a resource visible in the table must always be
    findable here too, regardless of which path served the list."""
    tenant_id = current_user["tenant_id"]
    if await mongo_available():
        collection = await _resources_collection()
        doc = await collection.find_one({"tenant_id": tenant_id, "id": resource_id}, {"_id": 0})
        if doc:
            return Resource(**doc)

    region = get_settings().aws_region
    direct = _live_aws_resource_by_id(resource_id, region, resource_type)
    if direct is not None:
        return direct

    for candidate in _live_aws_resources(region):
        if candidate.id == resource_id:
            return candidate
    return None


def _call_aws_detail(details: dict[str, Any], errors: dict[str, str], key: str, func):
    try:
        details[key] = jsonable_encoder(func())
    except ClientError as exc:
        error = exc.response.get("Error", {})
        errors[key] = f"{error.get('Code', 'ClientError')}: {error.get('Message', str(exc))}"
    except Exception as exc:  # noqa: BLE001 - this is a best-effort detail fanout
        errors[key] = str(exc)


def _live_aws_details(resource: Resource, settings) -> tuple[dict[str, Any], dict[str, str]]:
    if (resource.provider or "aws") != "aws":
        return {}, {}

    details: dict[str, Any] = {}
    errors: dict[str, str] = {}
    factory = AWSClientFactory(settings)
    region = resource.region or settings.aws_region
    resource_type = resource.resource_type or ""
    resource_id = resource.id

    if resource_type == "ec2_instance":
        ec2 = factory.client("ec2", region_name=region)
        autoscaling = factory.client("autoscaling", region_name=region)
        elbv2 = factory.client("elbv2", region_name=region)
        _call_aws_detail(details, errors, "describe_instances", lambda: ec2.describe_instances(InstanceIds=[resource_id]))
        _call_aws_detail(
            details,
            errors,
            "disable_api_termination",
            lambda: ec2.describe_instance_attribute(InstanceId=resource_id, Attribute="disableApiTermination"),
        )
        _call_aws_detail(
            details,
            errors,
            "attached_volumes",
            lambda: ec2.describe_volumes(Filters=[{"Name": "attachment.instance-id", "Values": [resource_id]}]),
        )
        _call_aws_detail(
            details,
            errors,
            "autoscaling_membership",
            lambda: autoscaling.describe_auto_scaling_instances(InstanceIds=[resource_id]),
        )

        def target_groups_for_instance():
            groups = elbv2.describe_target_groups().get("TargetGroups", [])
            matched = []
            for group in groups:
                try:
                    health = elbv2.describe_target_health(TargetGroupArn=group["TargetGroupArn"])
                except ClientError:
                    continue
                targets = [
                    item
                    for item in health.get("TargetHealthDescriptions", [])
                    if item.get("Target", {}).get("Id") == resource_id
                ]
                if targets:
                    matched.append({"target_group": group, "target_health": targets})
            return {"TargetGroups": matched}

        _call_aws_detail(details, errors, "load_balancer_targets", target_groups_for_instance)
    elif resource_type == "ebs_volume":
        ec2 = factory.client("ec2", region_name=region)
        _call_aws_detail(details, errors, "describe_volumes", lambda: ec2.describe_volumes(VolumeIds=[resource_id]))
        _call_aws_detail(
            details,
            errors,
            "volume_status",
            lambda: ec2.describe_volume_status(VolumeIds=[resource_id], IncludeAllVolumes=True),
        )
    elif resource_type == "rds_instance":
        rds = factory.client("rds", region_name=region)

        def db_instance():
            response = rds.describe_db_instances(DBInstanceIdentifier=resource_id)
            instances = response.get("DBInstances", [])
            if instances and instances[0].get("DBInstanceArn"):
                response["TagList"] = rds.list_tags_for_resource(ResourceName=instances[0]["DBInstanceArn"]).get("TagList", [])
            return response

        _call_aws_detail(details, errors, "describe_db_instances", db_instance)
    elif resource_type == "s3_bucket":
        s3 = factory.client("s3", region_name="us-east-1")
        bucket = resource_id
        _call_aws_detail(details, errors, "get_bucket_location", lambda: s3.get_bucket_location(Bucket=bucket))
        _call_aws_detail(details, errors, "get_bucket_tagging", lambda: s3.get_bucket_tagging(Bucket=bucket))
        _call_aws_detail(details, errors, "get_bucket_versioning", lambda: s3.get_bucket_versioning(Bucket=bucket))
        _call_aws_detail(details, errors, "get_bucket_encryption", lambda: s3.get_bucket_encryption(Bucket=bucket))
        _call_aws_detail(details, errors, "get_public_access_block", lambda: s3.get_public_access_block(Bucket=bucket))
        _call_aws_detail(details, errors, "get_bucket_policy_status", lambda: s3.get_bucket_policy_status(Bucket=bucket))
        _call_aws_detail(details, errors, "get_bucket_lifecycle_configuration", lambda: s3.get_bucket_lifecycle_configuration(Bucket=bucket))
        _call_aws_detail(details, errors, "get_bucket_logging", lambda: s3.get_bucket_logging(Bucket=bucket))
        _call_aws_detail(details, errors, "get_bucket_notification_configuration", lambda: s3.get_bucket_notification_configuration(Bucket=bucket))
    elif resource_type == "lambda_function":
        lambda_client = factory.client("lambda", region_name=region)
        _call_aws_detail(details, errors, "get_function", lambda: lambda_client.get_function(FunctionName=resource_id))
        _call_aws_detail(
            details,
            errors,
            "event_source_mappings",
            lambda: lambda_client.list_event_source_mappings(FunctionName=resource_id),
        )
        function_arn = details.get("get_function", {}).get("Configuration", {}).get("FunctionArn")
        if function_arn:
            _call_aws_detail(details, errors, "tags", lambda: lambda_client.list_tags(Resource=function_arn))
        _call_aws_detail(
            details,
            errors,
            "reserved_concurrency",
            lambda: lambda_client.get_function_concurrency(FunctionName=resource_id),
        )
        _call_aws_detail(details, errors, "resource_policy", lambda: lambda_client.get_policy(FunctionName=resource_id))
    elif resource_type == "dynamodb_table":
        dynamodb = factory.client("dynamodb", region_name=region)
        _call_aws_detail(details, errors, "describe_table", lambda: dynamodb.describe_table(TableName=resource_id))
        table_arn = details.get("describe_table", {}).get("Table", {}).get("TableArn")
        _call_aws_detail(
            details,
            errors,
            "continuous_backups",
            lambda: dynamodb.describe_continuous_backups(TableName=resource_id),
        )
        _call_aws_detail(details, errors, "time_to_live", lambda: dynamodb.describe_time_to_live(TableName=resource_id))
        if table_arn:
            _call_aws_detail(details, errors, "tags", lambda: dynamodb.list_tags_of_resource(ResourceArn=table_arn))
    elif resource_type == "cloudfront_distribution":
        cloudfront = factory.client("cloudfront", region_name="us-east-1")
        _call_aws_detail(details, errors, "get_distribution", lambda: cloudfront.get_distribution(Id=resource_id))
        _call_aws_detail(details, errors, "get_distribution_config", lambda: cloudfront.get_distribution_config(Id=resource_id))
    elif resource_type == "vpc":
        ec2 = factory.client("ec2", region_name=region)
        _call_aws_detail(details, errors, "describe_vpcs", lambda: ec2.describe_vpcs(VpcIds=[resource_id]))
        _call_aws_detail(
            details,
            errors,
            "subnets",
            lambda: ec2.describe_subnets(Filters=[{"Name": "vpc-id", "Values": [resource_id]}]),
        )
        _call_aws_detail(
            details,
            errors,
            "route_tables",
            lambda: ec2.describe_route_tables(Filters=[{"Name": "vpc-id", "Values": [resource_id]}]),
        )
        _call_aws_detail(
            details,
            errors,
            "internet_gateways",
            lambda: ec2.describe_internet_gateways(Filters=[{"Name": "attachment.vpc-id", "Values": [resource_id]}]),
        )
        _call_aws_detail(
            details,
            errors,
            "security_groups",
            lambda: ec2.describe_security_groups(Filters=[{"Name": "vpc-id", "Values": [resource_id]}]),
        )
        _call_aws_detail(
            details,
            errors,
            "nat_gateways",
            lambda: ec2.describe_nat_gateways(Filter=[{"Name": "vpc-id", "Values": [resource_id]}]),
        )
    elif resource_type == "security_group":
        ec2 = factory.client("ec2", region_name=region)
        _call_aws_detail(details, errors, "describe_security_groups", lambda: ec2.describe_security_groups(GroupIds=[resource_id]))
        _call_aws_detail(
            details,
            errors,
            "security_group_rules",
            lambda: ec2.describe_security_group_rules(Filters=[{"Name": "group-id", "Values": [resource_id]}]),
        )
    elif resource_type == "iam_user":
        iam = factory.client("iam", region_name="us-east-1")
        _call_aws_detail(details, errors, "get_user", lambda: iam.get_user(UserName=resource_id))
        _call_aws_detail(details, errors, "attached_policies", lambda: iam.list_attached_user_policies(UserName=resource_id))
        _call_aws_detail(details, errors, "inline_policies", lambda: iam.list_user_policies(UserName=resource_id))
        _call_aws_detail(details, errors, "access_keys", lambda: iam.list_access_keys(UserName=resource_id))
        _call_aws_detail(details, errors, "groups", lambda: iam.list_groups_for_user(UserName=resource_id))
        _call_aws_detail(details, errors, "mfa_devices", lambda: iam.list_mfa_devices(UserName=resource_id))

    return details, errors


@router.get("/tag-savings", response_model=TagSavingsResponse)
async def get_tag_savings(
    current_user: CurrentUser,
    tag_key: str = Query(default="Environment", min_length=1),
) -> TagSavingsResponse:
    settings = get_settings()
    account_id = settings.aws_account_id or "demo-account"
    region = settings.aws_region
    try:
        snapshot = AWSCollectorService(
            client_factory=AWSClientFactory(settings),
            region=region,
            account_id=account_id,
        ).collect_snapshot()
        return _tag_savings_from_snapshot(snapshot.model_dump(mode="json"), tag_key)
    except Exception as exc:
        logger.exception("resources: live tag-savings collection failed")
        return TagSavingsResponse(
            status="error",
            provider="aws",
            account_id=account_id,
            region=region,
            tag_key=tag_key,
            available_tag_keys=[tag_key],
            resources=0,
            findings=0,
            proposals=0,
            monthly_savings=0.0,
            groups=[],
            instances=[],
            error=str(exc),
        )


@router.get("/{resource_id}", response_model=ResourceDetail)
async def get_resource_detail(
    resource_id: str,
    current_user: CurrentUser,
    resource_type: str | None = None,
) -> ResourceDetail:
    """Everything known about one resource: the FOCUS cost rows that
    actually reference it (daily trend + top charge-description
    breakdown, not just the single monthly_cost_usd figure the table
    shows), its CloudWatch-derived utilization metric if one has been
    collected, and any proposal whose resource_arn ends in this id.
    Never fabricates a trend/breakdown when there's no FOCUS dataset or
    no matching rows — both come back as empty lists, which the frontend
    renders as "no cost rows for this resource" rather than a fake zero."""
    resource = await _find_resource(current_user, resource_id, resource_type)
    if resource is None:
        raise HTTPException(status_code=404, detail="Resource not found")

    tenant_id = current_user["tenant_id"]
    settings = get_settings()
    db = get_db()
    mongo_ok = await mongo_available()

    cost_trend: list[ResourceCostPoint] = []
    charge_breakdown: list[ResourceChargeBreakdownItem] = []
    focus_dataset_id: str | None = None
    focus_row_count = 0

    if mongo_ok:
        try:
            provider = resource.provider or "aws"
            account_id = settings.aws_account_id if provider == "aws" else ""
            dataset = await focus_repository.get_latest_dataset(db, tenant_id, provider, account_id)
        except Exception:
            logger.exception("resources: FOCUS dataset lookup failed for %s; cost trend/breakdown will be empty", resource_id)
            dataset = None
    else:
        dataset = None

    if dataset is not None:
        focus_dataset_id = dataset.dataset_id
        focus_row_count = sum(1 for row in dataset.records if row.ResourceId == resource_id)
        cost_trend, charge_breakdown = _build_cost_trend_and_breakdown(dataset.records, resource_id)

    if mongo_ok:
        try:
            metric = await get_resource_metric(db, tenant_id, resource_id)
        except Exception:
            logger.exception("resources: resource_metrics lookup failed for %s", resource_id)
            metric = None
    else:
        metric = None

    related_proposals: list[ActionProposal] = []
    if mongo_ok:
        try:
            # ARNs place the resource id at the end regardless of provider/service.
            # (".../instance/i-...", "arn:aws:s3:::bucket-name", ".../volume/vol-...")
        # — an anchored suffix match, not a plain substring, so "i-1" can't
        # match a proposal for "i-10".
            pattern = f"{re.escape(resource_id)}$"
            docs = await db.proposals.find(
                {"tenant_id": tenant_id, "resource_arn": {"$regex": pattern}}, {"_id": 0}
            ).to_list(length=None)
            related_proposals = [ActionProposal(**doc) for doc in docs]
        except Exception:
            logger.exception("resources: related-proposal lookup failed for %s", resource_id)

    try:
        aws_live_details, aws_live_errors = await asyncio.wait_for(
            asyncio.to_thread(_live_aws_details, resource, settings),
            timeout=12.0,
        )
    except TimeoutError:
        aws_live_details = {}
        aws_live_errors = {"timeout": "AWS live detail collection exceeded 12 seconds; retry after AWS credentials/network stabilize."}

    return ResourceDetail(
        resource=resource,
        metric=metric,
        cost_trend=cost_trend,
        charge_breakdown=charge_breakdown,
        focus_dataset_id=focus_dataset_id,
        focus_row_count=focus_row_count,
        related_proposals=related_proposals,
        raw_resource=jsonable_encoder(resource),
        aws_live_details=aws_live_details,
        aws_live_errors=aws_live_errors,
    )


@router.get("", response_model=list[Resource])
async def list_resources(
    current_user: CurrentUser,
    environment: str | None = None,
    status: str | None = None,
) -> list[Resource]:
    """List monitored resources, scoped to the caller's tenant (Days 5-7),
    optionally filtered by environment or status.

    Backed by MongoDB's `resources` collection. Once the collector service
    (blueprint 9.2/9.3) is writing real AWS inventory + CloudWatch data in,
    this query needs no further changes.
    """
    try:
        if not await mongo_available():
            resources = _live_aws_resources(get_settings().aws_region)
            if environment:
                resources = [resource for resource in resources if resource.environment == environment]
            if status:
                resources = [resource for resource in resources if resource.status == status]
            return resources

        collection = await _resources_collection()

        query: dict = {"tenant_id": current_user["tenant_id"]}
        if environment:
            query["environment"] = environment
        if status:
            query["status"] = status

        docs = await collection.find(query, {"_id": 0}).to_list(length=None)
        return [Resource(**doc) for doc in docs]
    except ExecutionRefused:
        raise
    except Exception as exc:
        logger.exception("resources: Mongo read failed; returning live AWS EC2 fallback")
        resources = _live_aws_resources(get_settings().aws_region)
        if environment:
            resources = [resource for resource in resources if resource.environment == environment]
        if status:
            resources = [resource for resource in resources if resource.status == status]
        return resources
