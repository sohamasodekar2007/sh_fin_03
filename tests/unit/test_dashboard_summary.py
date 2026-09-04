from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock

from services.focus.dashboard_summary import dashboard_cost_summary


def _mock_db(docs: list[dict]):
    mock_db = MagicMock()
    mock_collection = MagicMock()
    fake_cursor = MagicMock()
    fake_cursor.to_list = AsyncMock(return_value=docs)
    mock_collection.find.return_value = fake_cursor
    mock_db.focus_datasets = mock_collection
    return mock_db


def _record(**overrides) -> dict:
    now = overrides.pop("ChargePeriodStart")
    base = {
        "BillingAccountId": "acct-1",
        "BillingPeriodStart": now,
        "BillingPeriodEnd": now,
        "ChargePeriodStart": now,
        "ChargePeriodEnd": now,
        "ChargeCategory": "Usage",
        "ChargeDescription": "EC2 instance usage",
        "BilledCost": Decimal("10.00"),
        "EffectiveCost": Decimal("10.00"),
        "ProviderName": "AWS",
        "ResourceId": "i-abc123",
        "ServiceName": "Amazon Elastic Compute Cloud",
    }
    base.update(overrides)
    return base


def _dataset(tenant_id: str, provider: str, account_id: str, ingested_at: datetime, records: list[dict]) -> dict:
    return {
        "dataset_id": f"{provider}-{account_id}-{ingested_at.isoformat()}",
        "tenant_id": tenant_id,
        "provider": provider,
        "account_id": account_id,
        "focus_version": "1.0",
        "granularity": "daily",
        "ingested_at": ingested_at,
        "source": "sample",
        "row_count": len(records),
        "records": records,
    }


def test_no_datasets_returns_honest_empty_summary():
    db = _mock_db([])

    result = asyncio.run(dashboard_cost_summary(db, "demo-tenant", period_days=30))

    assert result["total_cost_usd"] is None
    assert result["prior_total_cost_usd"] is None
    assert result["resource_count"] == 0
    assert "message" in result


def test_current_period_cost_without_full_prior_window_leaves_prior_none():
    now = datetime.now(timezone.utc)
    records = [
        _record(ChargePeriodStart=now - timedelta(days=1), BilledCost=Decimal("100.00"), ResourceId="i-1"),
        _record(ChargePeriodStart=now - timedelta(days=5), BilledCost=Decimal("50.00"), ResourceId="i-2"),
    ]
    dataset = _dataset("demo-tenant", "aws", "acct-1", now, records)
    db = _mock_db([dataset])

    result = asyncio.run(dashboard_cost_summary(db, "demo-tenant", period_days=30))

    # Both records fall inside the current 30-day window; there is no data
    # reaching back into the prior window, so it must not be fabricated.
    assert result["total_cost_usd"] == 150.0
    assert result["prior_total_cost_usd"] is None
    assert result["resource_count"] == 2


def test_full_prior_window_computes_real_delta():
    now = datetime.now(timezone.utc)
    period_days = 30
    records = [
        _record(ChargePeriodStart=now - timedelta(days=5), BilledCost=Decimal("200.00"), ResourceId="i-1"),
        _record(ChargePeriodStart=now - timedelta(days=40), BilledCost=Decimal("150.00"), ResourceId="i-1"),
        _record(ChargePeriodStart=now - timedelta(days=65), BilledCost=Decimal("50.00"), ResourceId="i-2"),
    ]
    dataset = _dataset("demo-tenant", "aws", "acct-1", now, records)
    db = _mock_db([dataset])

    result = asyncio.run(dashboard_cost_summary(db, "demo-tenant", period_days=period_days))

    # day-5 record -> current window; day-40 -> prior window; day-65 sits
    # before the prior window itself but proves the data reaches back far
    # enough for the prior-period comparison to be a real one, not a
    # fabricated 100% delta from an empty denominator.
    assert result["total_cost_usd"] == 200.0
    assert result["prior_total_cost_usd"] == 150.0
    assert result["resource_count"] == 2


def test_only_latest_dataset_per_account_is_used():
    now = datetime.now(timezone.utc)
    older = _dataset(
        "demo-tenant", "aws", "acct-1", now - timedelta(hours=2),
        [_record(ChargePeriodStart=now - timedelta(days=1), BilledCost=Decimal("999.00"), ResourceId="stale")],
    )
    newer = _dataset(
        "demo-tenant", "aws", "acct-1", now,
        [_record(ChargePeriodStart=now - timedelta(days=1), BilledCost=Decimal("10.00"), ResourceId="fresh")],
    )
    db = _mock_db([older, newer])

    result = asyncio.run(dashboard_cost_summary(db, "demo-tenant", period_days=30))

    assert result["total_cost_usd"] == 10.0
    assert result["resource_count"] == 1


def test_distinct_accounts_are_summed_together():
    now = datetime.now(timezone.utc)
    aws_dataset = _dataset(
        "demo-tenant", "aws", "acct-1", now,
        [_record(ChargePeriodStart=now - timedelta(days=1), BilledCost=Decimal("10.00"), ResourceId="i-1")],
    )
    azure_dataset = _dataset(
        "demo-tenant", "azure", "acct-2", now,
        [_record(ChargePeriodStart=now - timedelta(days=1), BilledCost=Decimal("20.00"), ResourceId="i-2", ProviderName="Azure")],
    )
    db = _mock_db([aws_dataset, azure_dataset])

    result = asyncio.run(dashboard_cost_summary(db, "demo-tenant", period_days=30))

    assert result["total_cost_usd"] == 30.0
    assert result["resource_count"] == 2


def test_period_days_clamped_to_valid_range():
    db = _mock_db([])

    too_high = asyncio.run(dashboard_cost_summary(db, "demo-tenant", period_days=500))
    too_low = asyncio.run(dashboard_cost_summary(db, "demo-tenant", period_days=0))

    assert too_high["period_days"] == 90
    assert too_low["period_days"] == 1
