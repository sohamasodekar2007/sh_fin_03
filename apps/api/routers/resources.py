import asyncio
import logging
import re
import time
from typing import Any

from fastapi import APIRouter, Depends, HTTPException

from apps.api.config import get_settings
from apps.api.db import get_db
from apps.api.dependencies import CurrentUser
from apps.api.mock_data import RESOURCES
from packages.aws.session import AWSClientFactory
from packages.schemas.schemas import ActionProposal, Resource
from pydantic import BaseModel
from services.collector.collector_service import AWSCollectorService
from services.executor.actions import ExecutionRefused, assumed_write_session
from services.focus import repository as focus_repository
from services.focus.metrics import ResourceMetric, get_resource_metric

router = APIRouter(prefix="/v1/resources", tags=["resources"])
logger = logging.getLogger(__name__)
_MONGO_UNAVAILABLE_UNTIL = 0.0
_MONGO_RECHECK_SECONDS = 5.0


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
            resources.append(
                Resource(
                    id=resource_id,
                    type=raw.get("instance_type") or raw.get("type") or raw.get("resource_type") or "aws",
                    region=raw.get("region") or region,
                    cpu_p95=0.0,
                    status=_status_from_state(state),
                    monthly_cost_usd=None,
                    cost_source="no_focus_row",
                    focus_version=settings.focus_version,
                    focus_source="live",
                    focus_row_count=0,
                    resource_type=raw.get("resource_type"),
                    provider="aws",
                    state=state,
                    tags=tags,
                    environment=_dashboard_environment(raw.get("environment") or tags.get("Environment")),
                )
            )
        resources.sort(key=lambda item: (item.state != "running", item.tags.get("Name", ""), item.id))
        return resources
    except Exception:
        logger.exception("resources: full AWS fallback failed; using EC2-only fallback")

    session = assumed_write_session("resources-list-ec2")
    ec2 = session.client("ec2", region_name=region)
    resp = ec2.describe_instances()

    resources: list[Resource] = []
    for reservation in resp.get("Reservations", []):
        for instance in reservation.get("Instances", []):
            tags = _tags_to_dict(instance.get("Tags"))
            state = instance.get("State", {}).get("Name", "unknown")
            resources.append(
                Resource(
                    id=instance["InstanceId"],
                    type=instance.get("InstanceType", "ec2"),
                    region=region,
                    cpu_p95=0.0,
                    status=_status_from_state(state),
                    monthly_cost_usd=None,
                    cost_source="no_focus_row",
                    focus_version=settings.focus_version,
                    focus_source="live",
                    focus_row_count=0,
                    resource_type="ec2_instance",
                    provider="aws",
                    state=state,
                    tags=tags,
                    environment=_dashboard_environment(tags.get("Environment")),
                )
            )

    resources.sort(key=lambda item: (item.state != "running", item.tags.get("Name", ""), item.id))
    return resources


async def _resources_collection():
    """Returns the `resources` Mongo collection, auto-seeding it from
    mock_data.py the first time it's empty so the demo/dashboard never
    shows a blank screen while real AWS collection (Soham's track) is
    still being wired in."""
    db = get_db()
    if await db.resources.count_documents({}) == 0:
        await db.resources.insert_many([r.model_dump() for r in RESOURCES])
    return db.resources


async def _mongo_available(timeout_seconds: float = 1.5) -> bool:
    global _MONGO_UNAVAILABLE_UNTIL
    now = time.monotonic()
    if now < _MONGO_UNAVAILABLE_UNTIL:
        return False
    try:
        await asyncio.wait_for(get_db().client.admin.command("ping"), timeout=timeout_seconds)
        _MONGO_UNAVAILABLE_UNTIL = 0.0
        return True
    except Exception:
        _MONGO_UNAVAILABLE_UNTIL = time.monotonic() + _MONGO_RECHECK_SECONDS
        return False


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


async def _find_resource(current_user: CurrentUser, resource_id: str) -> Resource | None:
    """Same two-tier lookup as list_resources: Mongo first, live AWS
    fallback second — a resource visible in the table must always be
    findable here too, regardless of which path served the list."""
    tenant_id = current_user["tenant_id"]
    if await _mongo_available():
        collection = await _resources_collection()
        doc = await collection.find_one({"tenant_id": tenant_id, "id": resource_id}, {"_id": 0})
        if doc:
            return Resource(**doc)

    for candidate in _live_aws_resources(get_settings().aws_region):
        if candidate.id == resource_id:
            return candidate
    return None


@router.get("/{resource_id}", response_model=ResourceDetail)
async def get_resource_detail(resource_id: str, current_user: CurrentUser) -> ResourceDetail:
    """Everything known about one resource: the FOCUS cost rows that
    actually reference it (daily trend + top charge-description
    breakdown, not just the single monthly_cost_usd figure the table
    shows), its CloudWatch-derived utilization metric if one has been
    collected, and any proposal whose resource_arn ends in this id.
    Never fabricates a trend/breakdown when there's no FOCUS dataset or
    no matching rows — both come back as empty lists, which the frontend
    renders as "no cost rows for this resource" rather than a fake zero."""
    resource = await _find_resource(current_user, resource_id)
    if resource is None:
        raise HTTPException(status_code=404, detail="Resource not found")

    tenant_id = current_user["tenant_id"]
    settings = get_settings()
    db = get_db()

    cost_trend: list[ResourceCostPoint] = []
    charge_breakdown: list[ResourceChargeBreakdownItem] = []
    focus_dataset_id: str | None = None
    focus_row_count = 0

    try:
        provider = resource.provider or "aws"
        account_id = settings.aws_account_id if provider == "aws" else ""
        dataset = await focus_repository.get_latest_dataset(db, tenant_id, provider, account_id)
    except Exception:
        logger.exception("resources: FOCUS dataset lookup failed for %s; cost trend/breakdown will be empty", resource_id)
        dataset = None

    if dataset is not None:
        focus_dataset_id = dataset.dataset_id
        focus_row_count = sum(1 for row in dataset.records if row.ResourceId == resource_id)
        cost_trend, charge_breakdown = _build_cost_trend_and_breakdown(dataset.records, resource_id)

    try:
        metric = await get_resource_metric(db, tenant_id, resource_id)
    except Exception:
        logger.exception("resources: resource_metrics lookup failed for %s", resource_id)
        metric = None

    related_proposals: list[ActionProposal] = []
    try:
        # ARNs place the resource id at the end regardless of provider/service
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

    return ResourceDetail(
        resource=resource,
        metric=metric,
        cost_trend=cost_trend,
        charge_breakdown=charge_breakdown,
        focus_dataset_id=focus_dataset_id,
        focus_row_count=focus_row_count,
        related_proposals=related_proposals,
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
        if not await _mongo_available():
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
