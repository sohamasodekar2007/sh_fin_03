from __future__ import annotations

import sys
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
from unittest.mock import Mock, patch

import pytest

from packages.schemas.cloud_metrics import AzureResourceDailyCost
from packages.schemas.cloud_resource import AzureVMResourceRecord
from packages.schemas.focus import FocusRecord
from services.collector.mock_provider import generate_mock_observation_bundle
from services.focus.mappers import azure as azure_mapper
from services.focus.mappers.aws import map_snapshot_to_focus
from services.focus.sample_loader import load_sample_dataset

_REPO_ROOT = Path(__file__).resolve().parents[2]
_SAMPLE_FILE = _REPO_ROOT / ".focus-samples" / "FOCUS-1.0" / "focus_sample_100000.csv.gz"

requires_sample_data = pytest.mark.skipif(
    not _SAMPLE_FILE.exists(),
    reason="FOCUS-Sample-Data not cloned into .focus-samples/",
)


def _azure_vm(resource_id: str, name: str) -> AzureVMResourceRecord:
    return AzureVMResourceRecord(
        region="eastus",
        resource_group="rg1",
        resource_id=resource_id,
        name=name,
        environment="production",
        instance_type="Standard_D2s_v3",
        state="running",
        collected_at=datetime.now(timezone.utc),
        tags={"Environment": "prod"},
        warnings=[],
    )


def _build_azure_dataset(tenant_id: str = "demo-tenant"):
    """Builds a real Azure FocusDataset via the actual synthesis path,
    with only the SDK-facing collector calls mocked out — exercises the
    same code the live collectors feed in production."""
    factory = Mock()

    vm = _azure_vm("/subscriptions/sub-1/resourceGroups/rg1/providers/Microsoft.Compute/virtualMachines/vm1", "vm1")

    with (
        patch("services.focus.mappers.azure.AzureVMCollector") as mock_vm_collector_cls,
        patch("services.focus.mappers.azure.AzureDiskCollector") as mock_disk_collector_cls,
        patch("services.focus.mappers.azure.AzureCostCollector") as mock_cost_collector_cls,
    ):
        mock_vm_collector_cls.return_value.collect.return_value = [vm]
        mock_disk_collector_cls.return_value.collect.return_value = []
        mock_cost_collector_cls.return_value.collect_daily_costs.return_value = [
            AzureResourceDailyCost(resource_id=vm.resource_id, usage_date="2026-01-01", cost=Decimal("4.50"), currency="USD"),
            AzureResourceDailyCost(resource_id=vm.resource_id, usage_date="2026-01-02", cost=Decimal("4.75"), currency="USD"),
        ]

        return azure_mapper.map_account_to_focus(
            tenant_id, "sub-1", factory, focus_storage_account="", focus_container=""
        )


def _build_aws_dataset(tenant_id: str = "demo-tenant"):
    snapshot = generate_mock_observation_bundle(account_id="350381001148", region="ap-south-1")
    return map_snapshot_to_focus(snapshot.model_dump(mode="json"), tenant_id=tenant_id)


# ---------------------------------------------------------------------------
# Merged multi-provider dataset consistency
# ---------------------------------------------------------------------------


def test_aws_and_azure_datasets_carry_correct_provider_names():
    aws_dataset = _build_aws_dataset()
    azure_dataset = _build_azure_dataset()

    assert aws_dataset.provider == "aws"
    assert azure_dataset.provider == "azure"

    assert aws_dataset.row_count > 0
    assert azure_dataset.row_count > 0

    assert all(r.ProviderName == "AWS" for r in aws_dataset.records)
    assert all(r.ProviderName == "Microsoft" for r in azure_dataset.records)

    # No cross-contamination between the two datasets' records.
    aws_ids = {r.ResourceId for r in aws_dataset.records}
    azure_ids = {r.ResourceId for r in azure_dataset.records}
    assert aws_ids.isdisjoint(azure_ids)


def test_azure_dataset_uses_real_per_resource_cost_not_allocation():
    azure_dataset = _build_azure_dataset()

    for record in azure_dataset.records:
        assert record.extensions["x_allocation_method"] == "cost_management_actual_cost_per_resource"
        # Unlike AWS, Azure cost rows are never divided by resource count.
        assert "x_resource_count_in_snapshot" not in record.extensions


def test_merged_dataset_all_records_are_valid_focus_records_with_usd_currency():
    aws_dataset = _build_aws_dataset()
    azure_dataset = _build_azure_dataset()

    merged: list[FocusRecord] = [*aws_dataset.records, *azure_dataset.records]
    assert len(merged) > 0

    for record in merged:
        assert isinstance(record, FocusRecord)
        assert isinstance(record.BilledCost, Decimal)
        assert record.BillingCurrency == "USD"
        assert record.ChargePeriodStart.tzinfo is not None
        assert record.ChargePeriodEnd.tzinfo is not None
        assert record.ChargePeriodStart < record.ChargePeriodEnd
        assert record.ProviderName in ("AWS", "Microsoft")


@requires_sample_data
def test_merged_dataset_across_aws_azure_and_samples_has_consistent_provider_names():
    """The full multi-cloud picture: AWS + Azure both real (collector-shaped
    in AWS's case, collector-shaped-but-mocked in Azure's), plus GCP and
    Oracle still on FOCUS sample data — one merged list, every record
    still a valid, correctly-labeled FocusRecord."""
    aws_dataset = _build_aws_dataset()
    azure_dataset = _build_azure_dataset()
    gcp_dataset = load_sample_dataset("gcp", "demo-tenant", max_rows=10)
    oracle_dataset = load_sample_dataset("oracle", "demo-tenant", max_rows=10)

    merged: list[FocusRecord] = [
        *aws_dataset.records,
        *azure_dataset.records,
        *gcp_dataset.records,
        *oracle_dataset.records,
    ]

    provider_names = {r.ProviderName for r in merged}
    assert provider_names == {"AWS", "Microsoft", "Google Cloud", "Oracle"}

    # Every provider's slice of the merged dataset only contains that
    # provider's own real ProviderName — no mixing.
    assert all(r.ProviderName == "AWS" for r in aws_dataset.records)
    assert all(r.ProviderName == "Microsoft" for r in azure_dataset.records)
    assert all(r.ProviderName == "Google Cloud" for r in gcp_dataset.records)
    assert all(r.ProviderName == "Oracle" for r in oracle_dataset.records)

    # Every record across all four providers is a fully valid FocusRecord.
    for record in merged:
        assert isinstance(record, FocusRecord)
        assert isinstance(record.BilledCost, Decimal)
        assert record.ServiceName


@requires_sample_data
def test_merged_dataset_total_cost_sums_without_error_across_providers():
    """A Decimal sum across every provider's records should never raise —
    confirms no provider snuck a float or a different numeric type in."""
    aws_dataset = _build_aws_dataset()
    azure_dataset = _build_azure_dataset()
    gcp_dataset = load_sample_dataset("gcp", "demo-tenant", max_rows=10)

    merged: list[FocusRecord] = [*aws_dataset.records, *azure_dataset.records, *gcp_dataset.records]

    total = sum((r.BilledCost for r in merged), Decimal("0"))
    assert isinstance(total, Decimal)
    assert total >= Decimal("0") or total < Decimal("0")  # just proves it's a real Decimal, no exception


def test_azure_mapper_prefers_live_focus_export_over_synthesis_when_configured():
    """If AZURE_FOCUS_STORAGE_ACCOUNT/CONTAINER are set and the blob read
    succeeds, the mapper must use it (source="live_export") rather than
    falling through to collector-based synthesis."""
    factory = Mock()
    factory.credential.return_value = Mock()

    fake_blob = Mock(name="focus_export.csv", last_modified=datetime.now(timezone.utc))
    fake_blob.name = "focus_export.csv"
    csv_body = (
        b"BillingAccountId,BillingPeriodStart,BillingPeriodEnd,ChargePeriodStart,ChargePeriodEnd,"
        b"ChargeCategory,ChargeDescription,BilledCost,EffectiveCost,ProviderName,ServiceName\n"
        b"acct-1,2026-01-01 00:00:00,2026-02-01 00:00:00,2026-01-15 00:00:00,2026-01-16 00:00:00,"
        b"Usage,Native FOCUS export row,9.99,9.99,Microsoft,Virtual Machines\n"
    )

    mock_container_client = Mock()
    mock_container_client.list_blobs.return_value = [fake_blob]
    mock_container_client.download_blob.return_value.readall.return_value = csv_body

    fake_blob_module = Mock()
    fake_blob_module.ContainerClient = Mock(return_value=mock_container_client)

    with patch.dict(sys.modules, {"azure.storage.blob": fake_blob_module}):
        dataset = azure_mapper.map_account_to_focus(
            "demo-tenant", "acct-1", factory, focus_storage_account="cloudcarestorage", focus_container="focusexports"
        )

    assert dataset.source == "live_export"
    assert dataset.row_count == 1
    assert dataset.records[0].BilledCost == Decimal("9.99")
