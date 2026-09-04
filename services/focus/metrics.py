"""
Resource-level telemetry (CPU/memory/network), kept in a collection separate
from FOCUS billing rows and joined on ResourceId.

FOCUS 1.0 has no columns for CPU/memory utilization — it's a billing spec,
not a monitoring one — so telemetry never gets written into FocusRecord
columns. It lives here instead, and the Analyzer agent (Phase 3) joins the
two collections on ResourceId when it needs both cost and utilization for
the same resource (e.g. the idle/over-provisioned rules).
"""

from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import uuid4

from motor.motor_asyncio import AsyncIOMotorDatabase
from pydantic import BaseModel, Field

COLLECTION_NAME = "resource_metrics"


class ResourceMetric(BaseModel):
    metric_id: str = Field(default_factory=lambda: str(uuid4()))

    resource_id: str
    tenant_id: str

    window_start: datetime
    window_end: datetime

    cpu_p95: float | None = None
    cpu_avg: float | None = None
    mem_p95: float | None = None
    network_p95_bytes: float | None = None

    sample_count: int = 0


async def ensure_metrics_indexes(db: AsyncIOMotorDatabase) -> None:
    await db[COLLECTION_NAME].create_index(
        [("tenant_id", 1), ("resource_id", 1), ("window_end", -1)],
        name="tenant_resource_window",
    )


async def save_resource_metrics(db: AsyncIOMotorDatabase, metrics: list[ResourceMetric]) -> int:
    """Upserts one document per resource_id — each collector run replaces
    the previous window's reading for that resource rather than
    accumulating a new document every run."""
    if not metrics:
        return 0

    for metric in metrics:
        doc = metric.model_dump(mode="json")
        await db[COLLECTION_NAME].update_one(
            {"tenant_id": metric.tenant_id, "resource_id": metric.resource_id},
            {"$set": doc},
            upsert=True,
        )
    return len(metrics)


async def get_resource_metric(db: AsyncIOMotorDatabase, tenant_id: str, resource_id: str) -> ResourceMetric | None:
    doc = await db[COLLECTION_NAME].find_one({"tenant_id": tenant_id, "resource_id": resource_id}, {"_id": 0})
    if doc is None:
        return None
    return ResourceMetric(**doc)


async def list_resource_metrics(db: AsyncIOMotorDatabase, tenant_id: str) -> list[ResourceMetric]:
    cursor = db[COLLECTION_NAME].find({"tenant_id": tenant_id}, {"_id": 0})
    docs: list[dict[str, Any]] = await cursor.to_list(length=None)
    return [ResourceMetric(**doc) for doc in docs]
