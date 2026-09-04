"""
Real FOCUS-backed aggregation for the frontend dashboard's KpiStrip (Phase
10 item 1 — "Current monthly spend (FOCUS BilledCost, 30d)"). Deliberately
separate from services/chat/tools.py's get_cost_summary (Phase 7) even
though the core aggregation is similar — that function is tested chatbot
tool-call surface and this has a different contract (current AND prior
period, for a real delta, plus a distinct-resource count), so extending it
would risk the chatbot to serve the dashboard.

Never fabricates a "prior period" comparison: if there isn't a full prior
window of FOCUS data, prior_total_cost_usd comes back None, and the
caller (KpiStrip's Money delta) renders NOT_AVAILABLE rather than a
manufactured percentage.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import Any

from motor.motor_asyncio import AsyncIOMotorDatabase

from packages.schemas.focus import FocusDataset


async def _latest_datasets_by_account(db: AsyncIOMotorDatabase, tenant_id: str) -> list[FocusDataset]:
    docs = await db.focus_datasets.find({"tenant_id": tenant_id}, {"_id": 0}).to_list(length=None)
    latest_by_account: dict[tuple[str, str], dict[str, Any]] = {}
    for doc in docs:
        key = (doc.get("provider", ""), doc.get("account_id", ""))
        existing = latest_by_account.get(key)
        if existing is None or doc.get("ingested_at", "") > existing.get("ingested_at", ""):
            latest_by_account[key] = doc
    return [FocusDataset(**doc) for doc in latest_by_account.values()]


async def dashboard_cost_summary(db: AsyncIOMotorDatabase, tenant_id: str, period_days: int = 30) -> dict[str, Any]:
    period_days = max(1, min(period_days, 90))
    now = datetime.now(timezone.utc)
    current_cutoff = now - timedelta(days=period_days)
    prior_cutoff = current_cutoff - timedelta(days=period_days)

    datasets = await _latest_datasets_by_account(db, tenant_id)
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
        for record in dataset.records:
            if record.ResourceId:
                resource_ids.add(record.ResourceId)
            if earliest_record is None or record.ChargePeriodStart < earliest_record:
                earliest_record = record.ChargePeriodStart
            if record.ChargePeriodStart >= current_cutoff:
                current_total += record.BilledCost
            elif record.ChargePeriodStart >= prior_cutoff:
                prior_total += record.BilledCost

    # Only claim a prior-period comparison if the data actually reaches
    # back that far — otherwise an empty prior window would silently read
    # as "100% increase," which is fabricated, not computed.
    has_full_prior_window = earliest_record is not None and earliest_record <= prior_cutoff

    return {
        "period_days": period_days,
        "total_cost_usd": float(current_total),
        "prior_total_cost_usd": float(prior_total) if has_full_prior_window else None,
        "resource_count": len(resource_ids),
    }
