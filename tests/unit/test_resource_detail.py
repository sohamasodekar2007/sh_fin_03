"""Unit tests for the pure aggregation behind GET /v1/resources/{resource_id}
— apps/api/routers/resources.py's _build_cost_trend_and_breakdown. No
Mongo, no FastAPI, no auth: just FocusRecord instances in, ResourceDetail
sub-payloads out."""

from __future__ import annotations

from datetime import datetime, timezone

from apps.api.routers.resources import _build_cost_trend_and_breakdown
from packages.schemas.focus import FocusRecord


def _row(resource_id, day, cost, *, description="Compute", category="Usage", service="Amazon EC2"):
    ts = datetime(2026, 9, day, 12, 0, tzinfo=timezone.utc)
    return FocusRecord(
        BillingAccountId="123456789012",
        BillingPeriodStart=ts,
        BillingPeriodEnd=ts,
        ChargePeriodStart=ts,
        ChargePeriodEnd=ts,
        ChargeCategory=category,
        ChargeDescription=description,
        BilledCost=cost,
        EffectiveCost=cost,
        ProviderName="AWS",
        ServiceName=service,
        ResourceId=resource_id,
    )


def test_filters_to_only_the_requested_resource():
    records = [_row("i-1", 1, 10.0), _row("i-2", 1, 999.0)]
    trend, breakdown = _build_cost_trend_and_breakdown(records, "i-1")
    assert len(trend) == 1
    assert trend[0].billed_cost == 10.0
    assert len(breakdown) == 1


def test_groups_daily_cost_chronologically():
    records = [_row("i-1", 3, 5.0), _row("i-1", 1, 2.0), _row("i-1", 2, 3.0)]
    trend, _ = _build_cost_trend_and_breakdown(records, "i-1")
    assert [p.date for p in trend] == ["2026-09-01", "2026-09-02", "2026-09-03"]
    assert [p.billed_cost for p in trend] == [2.0, 3.0, 5.0]


def test_sums_multiple_rows_on_the_same_day():
    records = [_row("i-1", 1, 2.5), _row("i-1", 1, 1.5)]
    trend, _ = _build_cost_trend_and_breakdown(records, "i-1")
    assert len(trend) == 1
    assert trend[0].billed_cost == 4.0


def test_breakdown_groups_by_description_and_category_and_sorts_descending():
    records = [
        _row("i-1", 1, 10.0, description="Compute", category="Usage"),
        _row("i-1", 2, 5.0, description="Compute", category="Usage"),
        _row("i-1", 1, 200.0, description="Data Transfer", category="Usage"),
        _row("i-1", 1, 3.0, description="Compute", category="Tax"),
    ]
    _, breakdown = _build_cost_trend_and_breakdown(records, "i-1")
    assert breakdown[0].charge_description == "Data Transfer"
    assert breakdown[0].billed_cost == 200.0
    compute_usage = next(b for b in breakdown if b.charge_description == "Compute" and b.charge_category == "Usage")
    assert compute_usage.billed_cost == 15.0
    assert compute_usage.row_count == 2
    # Same description, different category, must not be merged together.
    assert any(b.charge_description == "Compute" and b.charge_category == "Tax" for b in breakdown)


def test_breakdown_caps_at_fifteen_rows():
    records = [_row("i-1", 1, float(i), description=f"charge-{i}") for i in range(1, 21)]
    _, breakdown = _build_cost_trend_and_breakdown(records, "i-1")
    assert len(breakdown) == 15
    assert breakdown[0].charge_description == "charge-20"  # highest cost first


def test_no_matching_rows_returns_empty_lists_not_an_error():
    records = [_row("i-999", 1, 100.0)]
    trend, breakdown = _build_cost_trend_and_breakdown(records, "i-1")
    assert trend == []
    assert breakdown == []


def test_empty_records_returns_empty_lists():
    trend, breakdown = _build_cost_trend_and_breakdown([], "i-1")
    assert trend == []
    assert breakdown == []
