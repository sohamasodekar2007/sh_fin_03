from __future__ import annotations

import asyncio
import csv
import gzip
from decimal import Decimal
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest

from packages.schemas.focus import FocusDataset, FocusRecord
from services.collector.mock_provider import generate_mock_observation_bundle
from services.focus import repository as focus_repository
from services.focus.mappers.aws import map_snapshot_to_focus
from services.focus.repository import _from_document, _to_document
from services.focus.sample_loader import (
    FocusSampleDataNotFoundError,
    load_sample_dataset,
)

_REPO_ROOT = Path(__file__).resolve().parents[2]
_SAMPLE_FILE = _REPO_ROOT / ".focus-samples" / "FOCUS-1.0" / "focus_sample_100000.csv.gz"

requires_sample_data = pytest.mark.skipif(
    not _SAMPLE_FILE.exists(),
    reason=(
        "FOCUS-Sample-Data not cloned into .focus-samples/. Run: git clone "
        "https://github.com/FinOps-Open-Cost-and-Usage-Spec/FOCUS-Sample-Data "
        ".focus-samples"
    ),
)


def _first_real_row() -> dict[str, str]:
    with gzip.open(_SAMPLE_FILE, "rt", newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        return next(reader)


# ---------------------------------------------------------------------------
# Round-trip a real sample CSV row through FocusRecord and back
# ---------------------------------------------------------------------------


@requires_sample_data
def test_real_sample_row_round_trips_without_data_loss():
    raw_row = _first_real_row()

    record, warnings = FocusRecord.from_raw(dict(raw_row))

    assert warnings == []

    # Cost columns: exact Decimal equality against the raw CSV string, not
    # string equality (Decimal("0.00000000000") canonicalizes to "0E-11").
    assert record.BilledCost == Decimal(raw_row["BilledCost"])
    assert record.EffectiveCost == Decimal(raw_row["EffectiveCost"])

    # Identity columns survive verbatim.
    assert record.BillingAccountId == raw_row["BillingAccountId"]
    assert record.ProviderName == raw_row["ProviderName"]
    assert record.ServiceName == raw_row["ServiceName"]
    assert record.ChargeDescription == raw_row["ChargeDescription"]

    # The one non-spec column in the real file lands in extensions, not
    # dropped and not silently promoted to a typed field.
    assert record.extensions["Id"] == raw_row["Id"]

    # datetimes are tz-aware and match the source instant.
    assert record.ChargePeriodStart.tzinfo is not None
    assert record.ChargePeriodStart.isoformat().startswith(raw_row["ChargePeriodStart"].replace(" ", "T"))


@requires_sample_data
def test_sample_loader_reads_all_four_providers():
    seen_providers = {}
    for provider in ("aws", "azure", "gcp", "oracle"):
        dataset = load_sample_dataset(provider, tenant_id="demo-tenant", max_rows=20)
        seen_providers[provider] = dataset.row_count
        assert dataset.source == "sample"
        assert dataset.tenant_id == "demo-tenant"
        assert dataset.provider == provider
        for record in dataset.records:
            assert isinstance(record.BilledCost, Decimal)

    # AWS/Microsoft/Oracle have plenty of rows; Google Cloud has only 2 in
    # the entire 100k sample, so it alone is allowed to come back short.
    assert seen_providers["aws"] == 20
    assert seen_providers["azure"] == 20
    assert seen_providers["oracle"] == 20
    assert 0 < seen_providers["gcp"] <= 20


def test_sample_loader_unknown_provider_raises_value_error(tmp_path):
    with pytest.raises(ValueError):
        load_sample_dataset("vps", tenant_id="demo-tenant")


def test_sample_loader_missing_clone_raises_not_found(tmp_path):
    with pytest.raises(FocusSampleDataNotFoundError):
        load_sample_dataset("aws", tenant_id="demo-tenant", sample_dir=tmp_path)


# ---------------------------------------------------------------------------
# A CloudSnapshot fixture maps to the expected number of FOCUS rows
# ---------------------------------------------------------------------------


def test_aws_mapper_produces_one_row_per_resource_per_cost_day():
    snapshot = generate_mock_observation_bundle(account_id="350381001148", region="ap-south-1")
    snapshot_dict = snapshot.model_dump(mode="json")

    dataset = map_snapshot_to_focus(snapshot_dict, tenant_id="demo-tenant")

    expected_rows = len(snapshot_dict["resources"]) * len(snapshot_dict["daily_costs"])
    assert dataset.row_count == expected_rows
    assert len(dataset.records) == expected_rows
    assert dataset.source == "synthesized"
    assert dataset.granularity == "daily"
    assert dataset.provider == "aws"
    assert dataset.warnings == []


def test_aws_mapper_allocation_reconciles_to_account_total():
    snapshot = generate_mock_observation_bundle(account_id="350381001148", region="ap-south-1")
    snapshot_dict = snapshot.model_dump(mode="json")

    dataset = map_snapshot_to_focus(snapshot_dict, tenant_id="demo-tenant")

    total_focus_cost = sum((r.BilledCost for r in dataset.records), Decimal("0"))
    total_daily_cost = sum(
        (Decimal(str(d["amount"])) for d in snapshot_dict["daily_costs"]), Decimal("0")
    )
    assert abs(total_focus_cost - total_daily_cost) < Decimal("0.01")

    # Every synthesized row must disclose that it's an allocation, not an
    # observed per-resource cost.
    for record in dataset.records:
        assert record.extensions["x_allocation_method"] == "equal_split_of_account_daily_cost"


def test_aws_mapper_routes_ebs_volumes_to_storage_category():
    snapshot = generate_mock_observation_bundle(account_id="350381001148", region="ap-south-1")
    snapshot_dict = snapshot.model_dump(mode="json")

    dataset = map_snapshot_to_focus(snapshot_dict, tenant_id="demo-tenant")

    ebs_records = [r for r in dataset.records if r.ResourceType == "ebs_volume"]
    ec2_records = [r for r in dataset.records if r.ResourceType == "ec2_instance"]

    assert ebs_records, "mock snapshot should contain unattached EBS volumes"
    assert all(r.ServiceCategory == "Storage" for r in ebs_records)
    assert all(r.ServiceCategory == "Compute" for r in ec2_records)


def test_aws_mapper_empty_snapshot_produces_no_rows_with_warning():
    dataset = map_snapshot_to_focus(
        {"account_id": "123", "region": "us-east-1", "resources": [], "daily_costs": []},
        tenant_id="demo-tenant",
    )
    assert dataset.row_count == 0
    assert dataset.records == []
    assert "empty_snapshot_no_resources_or_costs" in dataset.warnings


# ---------------------------------------------------------------------------
# A record missing a required column produces a warning, not an exception
# ---------------------------------------------------------------------------


def test_missing_required_column_warns_without_raising():
    incomplete_row = {
        "BillingAccountId": "",
        "ChargeDescription": "test charge",
        "BilledCost": "1.00",
        "EffectiveCost": "1.00",
        "ProviderName": "AWS",
        "ServiceName": "Test Service",
        "ChargeCategory": "Usage",
        "ChargePeriodStart": "2024-09-01 00:00:00",
        "ChargePeriodEnd": "2024-09-01 01:00:00",
        # BillingPeriodStart/End deliberately omitted
    }

    warnings = FocusRecord.validate_record(incomplete_row)
    assert "missing_required_column:BillingAccountId" in warnings
    assert "missing_required_column:BillingPeriodStart" in warnings
    assert "missing_required_column:BillingPeriodEnd" in warnings

    # from_raw() must still produce a usable record — never raise.
    record, from_raw_warnings = FocusRecord.from_raw(incomplete_row)
    assert isinstance(record, FocusRecord)
    assert "missing_required_column:BillingAccountId" in from_raw_warnings


def test_negative_billed_cost_on_credit_row_is_not_flagged():
    credit_row = {
        "BillingAccountId": "123",
        "BillingPeriodStart": "2024-09-01 00:00:00",
        "BillingPeriodEnd": "2024-10-01 00:00:00",
        "ChargePeriodStart": "2024-09-01 00:00:00",
        "ChargePeriodEnd": "2024-09-01 01:00:00",
        "ChargeCategory": "Credit",
        "ChargeDescription": "refund",
        "BilledCost": "-5.00",
        "EffectiveCost": "-5.00",
        "ProviderName": "AWS",
        "ServiceName": "Test Service",
    }
    warnings = FocusRecord.validate_record(credit_row)
    assert "negative_billed_cost_on_non_credit_row" not in warnings


def test_negative_billed_cost_on_usage_row_is_flagged_but_not_dropped():
    usage_row = {
        "BillingAccountId": "123",
        "BillingPeriodStart": "2024-09-01 00:00:00",
        "BillingPeriodEnd": "2024-10-01 00:00:00",
        "ChargePeriodStart": "2024-09-01 00:00:00",
        "ChargePeriodEnd": "2024-09-01 01:00:00",
        "ChargeCategory": "Usage",
        "ChargeDescription": "usage-based refund adjustment",
        "BilledCost": "-0.02",
        "EffectiveCost": "-0.02",
        "ProviderName": "AWS",
        "ServiceName": "Test Service",
    }
    warnings = FocusRecord.validate_record(usage_row)
    assert "negative_billed_cost_on_non_credit_row" in warnings

    record, _ = FocusRecord.from_raw(usage_row)
    assert record.BilledCost == Decimal("-0.02")


def test_currency_mismatch_is_flagged():
    row = {
        "BillingAccountId": "123",
        "BillingPeriodStart": "2024-09-01 00:00:00",
        "BillingPeriodEnd": "2024-10-01 00:00:00",
        "ChargePeriodStart": "2024-09-01 00:00:00",
        "ChargePeriodEnd": "2024-09-01 01:00:00",
        "ChargeCategory": "Usage",
        "ChargeDescription": "test",
        "BilledCost": "1.00",
        "EffectiveCost": "1.00",
        "ProviderName": "AWS",
        "ServiceName": "Test Service",
        "BillingCurrency": "INR",
    }
    warnings = FocusRecord.validate_record(row)
    assert "currency_mismatch:INR" in warnings


# ---------------------------------------------------------------------------
# Decimal precision is preserved (no float rounding on cost columns)
# ---------------------------------------------------------------------------


def test_decimal_precision_preserved_on_high_precision_cost():
    row = {
        "BillingAccountId": "123",
        "BillingPeriodStart": "2024-09-01 00:00:00",
        "BillingPeriodEnd": "2024-10-01 00:00:00",
        "ChargePeriodStart": "2024-09-01 00:00:00",
        "ChargePeriodEnd": "2024-09-01 01:00:00",
        "ChargeCategory": "Usage",
        "ChargeDescription": "sub-cent AWS charge",
        "BilledCost": "0.00000080000",
        "EffectiveCost": "0.00000080000",
        "ProviderName": "AWS",
        "ServiceName": "Test Service",
    }
    record, _ = FocusRecord.from_raw(row)

    # Exact Decimal equality (Decimal itself may reformat the string into
    # scientific notation for small magnitudes — e.g. "8.0000E-7" instead of
    # "0.00000080000" — but that is a display difference, not lost
    # precision: both have the same 5 significant figures).
    assert record.BilledCost == Decimal("0.00000080000")
    assert record.BilledCost.as_tuple() == Decimal("0.00000080000").as_tuple()


def test_repository_document_round_trip_preserves_decimal_and_datetime():
    snapshot = generate_mock_observation_bundle(account_id="350381001148", region="ap-south-1")
    dataset = map_snapshot_to_focus(snapshot.model_dump(mode="json"), tenant_id="demo-tenant")

    document = _to_document(dataset)
    restored = _from_document(document)

    assert restored.row_count == dataset.row_count
    for original, round_tripped in zip(dataset.records, restored.records):
        assert original.BilledCost == round_tripped.BilledCost
        assert original.ChargePeriodStart == round_tripped.ChargePeriodStart
        assert round_tripped.ChargePeriodStart.tzinfo is not None


# ---------------------------------------------------------------------------
# FocusDataset.validate_record edge cases
# ---------------------------------------------------------------------------


def test_service_category_normalizes_others_to_other():
    row = {
        "BillingAccountId": "123",
        "BillingPeriodStart": "2024-09-01 00:00:00",
        "BillingPeriodEnd": "2024-10-01 00:00:00",
        "ChargePeriodStart": "2024-09-01 00:00:00",
        "ChargePeriodEnd": "2024-09-01 01:00:00",
        "ChargeCategory": "Usage",
        "ChargeDescription": "test",
        "BilledCost": "1.00",
        "EffectiveCost": "1.00",
        "ProviderName": "AWS",
        "ServiceName": "Test Service",
        "ServiceCategory": "Others",
    }
    record, _ = FocusRecord.from_raw(row)
    assert record.ServiceCategory == "Other"


def test_tags_json_string_parses_to_dict():
    row = {
        "BillingAccountId": "123",
        "BillingPeriodStart": "2024-09-01 00:00:00",
        "BillingPeriodEnd": "2024-10-01 00:00:00",
        "ChargePeriodStart": "2024-09-01 00:00:00",
        "ChargePeriodEnd": "2024-09-01 01:00:00",
        "ChargeCategory": "Usage",
        "ChargeDescription": "test",
        "BilledCost": "1.00",
        "EffectiveCost": "1.00",
        "ProviderName": "AWS",
        "ServiceName": "Test Service",
        "Tags": '{"environment": "prod"}',
    }
    record, _ = FocusRecord.from_raw(row)
    assert record.Tags == {"environment": "prod"}


def test_tags_null_literal_becomes_empty_dict():
    row = {
        "BillingAccountId": "123",
        "BillingPeriodStart": "2024-09-01 00:00:00",
        "BillingPeriodEnd": "2024-10-01 00:00:00",
        "ChargePeriodStart": "2024-09-01 00:00:00",
        "ChargePeriodEnd": "2024-09-01 01:00:00",
        "ChargeCategory": "Usage",
        "ChargeDescription": "test",
        "BilledCost": "1.00",
        "EffectiveCost": "1.00",
        "ProviderName": "AWS",
        "ServiceName": "Test Service",
        "Tags": "NULL",
    }
    record, _ = FocusRecord.from_raw(row)
    assert record.Tags == {}


# ---------------------------------------------------------------------------
# Mongo persistence (mocked — no local MongoDB required)
# ---------------------------------------------------------------------------


def test_ensure_indexes_creates_expected_indexes():
    mock_db = MagicMock()
    mock_collection = MagicMock()
    mock_collection.create_index = AsyncMock()
    mock_db.__getitem__.return_value = mock_collection

    asyncio.run(focus_repository.ensure_indexes(mock_db))

    assert mock_collection.create_index.await_count == 2
    first_call, second_call = mock_collection.create_index.await_args_list
    assert first_call.args[0] == [
        ("tenant_id", 1), ("provider", 1), ("account_id", 1), ("ingested_at", -1),
    ]
    assert second_call.args[0] == [("tenant_id", 1), ("records.ResourceId", 1)]


def test_save_dataset_inserts_one_document():
    snapshot = generate_mock_observation_bundle(account_id="350381001148", region="ap-south-1")
    dataset = map_snapshot_to_focus(snapshot.model_dump(mode="json"), tenant_id="demo-tenant")

    mock_db = MagicMock()
    mock_collection = MagicMock()
    mock_collection.insert_one = AsyncMock()
    mock_db.__getitem__.return_value = mock_collection

    returned_id = asyncio.run(focus_repository.save_dataset(mock_db, dataset))

    assert returned_id == dataset.dataset_id
    mock_collection.insert_one.assert_awaited_once()
    inserted_doc = mock_collection.insert_one.await_args.args[0]
    assert inserted_doc["dataset_id"] == dataset.dataset_id
    assert isinstance(inserted_doc["records"][0]["BilledCost"], str)  # Decimal -> str at the boundary


def test_get_latest_dataset_returns_none_when_absent():
    mock_db = MagicMock()
    mock_collection = MagicMock()
    mock_collection.find_one = AsyncMock(return_value=None)
    mock_db.__getitem__.return_value = mock_collection

    result = asyncio.run(focus_repository.get_latest_dataset(mock_db, "demo-tenant", "aws", "123"))

    assert result is None
    mock_collection.find_one.assert_awaited_once_with(
        {"tenant_id": "demo-tenant", "provider": "aws", "account_id": "123"},
        sort=[("ingested_at", -1)],
    )


def test_get_latest_dataset_reconstructs_focus_dataset():
    snapshot = generate_mock_observation_bundle(account_id="350381001148", region="ap-south-1")
    dataset = map_snapshot_to_focus(snapshot.model_dump(mode="json"), tenant_id="demo-tenant")
    document = _to_document(dataset)
    document["_id"] = "some-mongo-object-id"

    mock_db = MagicMock()
    mock_collection = MagicMock()
    mock_collection.find_one = AsyncMock(return_value=document)
    mock_db.__getitem__.return_value = mock_collection

    result = asyncio.run(
        focus_repository.get_latest_dataset(mock_db, "demo-tenant", "aws", dataset.account_id)
    )

    assert isinstance(result, FocusDataset)
    assert result.dataset_id == dataset.dataset_id
    assert result.row_count == dataset.row_count
