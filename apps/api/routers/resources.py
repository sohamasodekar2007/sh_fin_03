from fastapi import APIRouter, Depends

from apps.api.db import get_db
from apps.api.dependencies import CurrentUser
from apps.api.mock_data import RESOURCES
from packages.schemas.schemas import Resource

router = APIRouter(prefix="/v1/resources", tags=["resources"])


async def _resources_collection():
    """Returns the `resources` Mongo collection, auto-seeding it from
    mock_data.py the first time it's empty so the demo/dashboard never
    shows a blank screen while real AWS collection (Soham's track) is
    still being wired in."""
    db = get_db()
    if await db.resources.count_documents({}) == 0:
        await db.resources.insert_many([r.model_dump() for r in RESOURCES])
    return db.resources


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
    collection = await _resources_collection()

    query: dict = {"tenant_id": current_user["tenant_id"]}
    if environment:
        query["environment"] = environment
    if status:
        query["status"] = status

    docs = await collection.find(query, {"_id": 0}).to_list(length=None)
    return [Resource(**doc) for doc in docs]
