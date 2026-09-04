"""
FOCUS-backed dashboard cost aggregation.

This endpoint sits on the dashboard hot path, so it intentionally avoids
Pydantic-validating every embedded FOCUS row. Ingest already validates rows;
the dashboard only needs a small aggregate.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation
from typing import Any

from motor.motor_asyncio import AsyncIOMotorDatabase


async def _latest_dataset_docs_by_account(db: AsyncIOMotorDatabase, tenant_id: str) -> list[dict[str, Any]]:
    pipeline = [
        {"$match": {"tenant_id": tenant_id}},
        {"$sort": {"provider": 1, "account_id": 1, "ingested_at": -1}},
        {"$group": {"_id": {"provider": "$provider", "account_id": "$account_id"}, "doc": {"$first": "$$ROOT"}}},
        {"$replaceRoot": {"newRoot": "$doc"}},
        {"$project": {"_id": 0, "provider": 1, "account_id": 1, "ingested_at": 1, "records": 1}},
    ]
    try:
        return await db.focus_datasets.aggregate(pipeline, allowDiskUse=True).to_list(length=None)
    except (AttributeError, TypeError):
        docs = await db.focus_datasets.find({"tenant_id": tenant_id}, {"_id": 0}).to_list(length=None)
        latest_by_account: dict[tuple[str, str], dict[str, Any]] = {}
        for doc in docs:
            key = (doc.get("provider", ""), doc.get("account_id", ""))
            existing = latest_by_account.get(key)
            if existing is None or doc.get("ingested_at", "") > existing.get("ingested_at", ""):
                latest_by_account[key] = doc
        return list(latest_by_account.values())


def _as_datetime(value: Any) -> datetime | None:
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    if isinstance(value, str):
        try:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return None
        return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)
    return None


def _as_decimal(value: Any) -> Decimal:
    if isinstance(value, Decimal):
        return value
    if hasattr(value, "to_decimal"):
        return value.to_decimal()
    try:
        return Decimal(str(value or "0"))
    except (InvalidOperation, ValueError):
        return Decimal("0")


async def dashboard_cost_summary(db: AsyncIOMotorDatabase, tenant_id: str, period_days: int = 30) -> dict[str, Any]:
    period_days = max(1, min(period_days, 90))
    now = datetime.now(timezone.utc)
    current_cutoff = now - timedelta(days=period_days)
    prior_cutoff = current_cutoff - timedelta(days=period_days)

    datasets = await _latest_dataset_docs_by_account(db, tenant_id)
    if not datasets:
        return {
            "period_days": period_days,
            "total_cost_usd": None,
            "prior_total_cost_usd": None,
            "resource_count": 0,
            "message": "No FOCUS data ingested yet for this tenant.",
        }

    current_total = Decimal("0")
    prior_total = Decimal("0")
    resource_ids: set[str] = set()
    earliest_record: datetime | None = None

    for dataset in datasets:
        for record in dataset.get("records") or []:
            resource_id = record.get("ResourceId")
            if resource_id:
                resource_ids.add(str(resource_id))

            charge_start = _as_datetime(record.get("ChargePeriodStart"))
            if charge_start is None:
                continue

            if earliest_record is None or charge_start < earliest_record:
                earliest_record = charge_start

            billed_cost = _as_decimal(record.get("BilledCost"))
            if charge_start >= current_cutoff:
                current_total += billed_cost
            elif charge_start >= prior_cutoff:
                prior_total += billed_cost

    has_full_prior_window = earliest_record is not None and earliest_record <= prior_cutoff

    return {
        "period_days": period_days,
        "total_cost_usd": float(current_total),
        "prior_total_cost_usd": float(prior_total) if has_full_prior_window else None,
        "resource_count": len(resource_ids),
    }
