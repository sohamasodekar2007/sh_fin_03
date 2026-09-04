from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal

from apps.api.routers.observation import _cost_by_resource_id
from packages.schemas.focus import FocusDataset


def _record(resource_id: str | None, billed_cost: str) -> dict:
    now = datetime.now(timezone.utc)
    return {
        "BillingAccountId": "acct-1",
        "BillingPeriodStart": now,
        "BillingPeriodEnd": now,
        "ChargePeriodStart": now,
        "ChargePeriodEnd": now,
        "ChargeCategory": "Usage",
        "ChargeDescription": "EC2 instance usage",
        "BilledCost": Decimal(billed_cost),
        "EffectiveCost": Decimal(billed_cost),
        "ProviderName": "AWS",
        "ResourceId": resource_id,
        "ServiceName": "Amazon Elastic Compute Cloud",
    }


def _dataset(records: list[dict]) -> FocusDataset:
    return FocusDataset(
        tenant_id="demo-tenant",
        provider="aws",
        account_id="123",
        source="live_export",
        row_count=len(records),
        records=records,
    )


def test_none_dataset_returns_empty_map():
    assert _cost_by_resource_id(None) == {}


def test_sums_multiple_charge_rows_for_the_same_resource():
    dataset = _dataset([
        _record("i-1", "10.00"),
        _record("i-1", "5.50"),
        _record("i-2", "3.00"),
    ])

    result = _cost_by_resource_id(dataset)

    assert result["i-1"] == 15.5
    assert result["i-2"] == 3.0


def test_records_without_a_resource_id_are_skipped_not_lumped_together():
    dataset = _dataset([
        _record(None, "100.00"),  # e.g. a Tax line with no resource attribution
        _record("i-1", "1.00"),
    ])

    result = _cost_by_resource_id(dataset)

    assert result == {"i-1": 1.0}


def test_resource_with_no_matching_record_is_absent_not_zero():
    dataset = _dataset([_record("i-1", "1.00")])

    result = _cost_by_resource_id(dataset)

    # A resource not in the map means "no observed cost this period" — the
    # caller (observation.py) must use .get() and leave it None, never
    # default it to 0.0 (which would look like a real, confirmed-zero cost).
    assert "i-2" not in result
