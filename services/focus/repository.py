"""
Mongo persistence for FOCUS datasets.

One document per ingestion run in `focus_datasets`, records embedded (per
the phase spec). Decimal cost columns can't be encoded by pymongo directly,
so writes go through FocusDataset.model_dump(mode="json") — which serializes
every Decimal as a string via Pydantic's JSON encoder — and reads go through
FocusDataset(**doc), which parses those strings straight back into Decimal.
This is the "convert at the boundary, pick one, be consistent" approach:
the boundary is exactly these two functions, nowhere else.
"""

from __future__ import annotations

from typing import Any

from motor.motor_asyncio import AsyncIOMotorDatabase

from packages.schemas.focus import FocusDataset

COLLECTION_NAME = "focus_datasets"


async def ensure_indexes(db: AsyncIOMotorDatabase) -> None:
    collection = db[COLLECTION_NAME]
    await collection.create_index(
        [("tenant_id", 1), ("provider", 1), ("account_id", 1), ("ingested_at", -1)],
        name="tenant_provider_account_ingested",
    )
    await collection.create_index(
        [("tenant_id", 1), ("records.ResourceId", 1)],
        name="tenant_resource_id",
    )


def _to_document(dataset: FocusDataset) -> dict[str, Any]:
    return dataset.model_dump(mode="json")


def _from_document(doc: dict[str, Any]) -> FocusDataset:
    doc = dict(doc)
    doc.pop("_id", None)
    return FocusDataset(**doc)


async def save_dataset(db: AsyncIOMotorDatabase, dataset: FocusDataset) -> str:
    """Insert one document per ingestion run. Returns the inserted dataset_id."""
    await db[COLLECTION_NAME].insert_one(_to_document(dataset))
    return dataset.dataset_id


async def get_latest_dataset(
    db: AsyncIOMotorDatabase,
    tenant_id: str,
    provider: str,
    account_id: str,
) -> FocusDataset | None:
    doc = await db[COLLECTION_NAME].find_one(
        {"tenant_id": tenant_id, "provider": provider, "account_id": account_id},
        sort=[("ingested_at", -1)],
    )
    if doc is None:
        return None
    return _from_document(doc)


async def get_dataset_by_id(db: AsyncIOMotorDatabase, dataset_id: str) -> FocusDataset | None:
    doc = await db[COLLECTION_NAME].find_one({"dataset_id": dataset_id})
    if doc is None:
        return None
    return _from_document(doc)
