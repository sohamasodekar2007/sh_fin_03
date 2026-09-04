import asyncio
import logging
import time
from typing import Any

from fastapi import APIRouter, Depends

from apps.api.config import get_settings
from apps.api.db import get_db
from apps.api.dependencies import CurrentUser
from apps.api.mock_data import RESOURCES
from packages.aws.session import AWSClientFactory
from packages.schemas.schemas import Resource
from services.collector.collector_service import AWSCollectorService
from services.executor.actions import ExecutionRefused, assumed_write_session

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
