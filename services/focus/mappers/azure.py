"""
Maps Azure billing data into FOCUS 1.0 rows.

SOURCE STRATEGY (both, with fallback): if AZURE_FOCUS_STORAGE_ACCOUNT and
AZURE_FOCUS_CONTAINER are configured, read the Cost Management FOCUS 1.0
export blobs directly — Azure emits FOCUS natively, so that path is column
validation (FocusRecord.from_raw), not translation. Otherwise synthesize
FOCUS rows from services/collector/azure/{vm,disk,cost}_collector.py.

Unlike AWS (services/focus/mappers/aws.py), whose Cost Explorer data has no
resource dimension and has to equal-split each day's account total across
resources, Azure's Cost Management API groups ActualCost by ResourceId
directly — so synthesis here carries a real per-resource cost, not an
allocation. Every synthesized row is still tagged with
extensions["x_allocation_method"] for provenance, but its value reflects
that this is an observed per-resource cost, not a split.

This mapper assumes `connected=True` for the account (see
CloudAccount.connected) — apps/api/routers/observation.py is responsible
for falling back to services/focus/mappers/... sample data when Azure isn't
connected yet, or when this mapper's collection comes back completely empty
(e.g. bad credentials), the same way it already falls back to synthetic
data for AWS.
"""

from __future__ import annotations

import csv
import gzip
import io
import logging
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from typing import Any

from packages.azure.session import AzureClientFactory
from packages.schemas.cloud_metrics import AzureResourceDailyCost
from packages.schemas.focus import FocusDataset, FocusRecord
from services.collector.azure.cost_collector import AzureCostCollectionError, AzureCostCollector
from services.collector.azure.disk_collector import AzureDiskCollectionError, AzureDiskCollector
from services.collector.azure.vm_collector import AzureVMCollectionError, AzureVMCollector

logger = logging.getLogger(__name__)


def _service_fields(resource_type: str | None) -> tuple[str, str]:
    """(ServiceName, ServiceCategory) for a CloudCare Azure resource_type."""
    if resource_type == "azure_disk":
        return "Managed Disks", "Storage"
    return "Virtual Machines", "Compute"


def _billing_period_bounds(charge_start: datetime) -> tuple[datetime, datetime]:
    month_start = charge_start.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    if month_start.month == 12:
        next_month_start = month_start.replace(year=month_start.year + 1, month=1)
    else:
        next_month_start = month_start.replace(month=month_start.month + 1)
    return month_start, next_month_start


def _synthesize_from_collectors(
    tenant_id: str,
    account_id: str,
    client_factory: AzureClientFactory,
) -> FocusDataset:
    warnings: list[str] = []

    vm_collector = AzureVMCollector(client_factory)
    disk_collector = AzureDiskCollector(client_factory)
    cost_collector = AzureCostCollector(client_factory)

    try:
        vms = vm_collector.collect()
    except AzureVMCollectionError as err:
        logger.warning("azure.focus_mapper: VM collection failed: %s", err)
        warnings.append(f"vm_collection_failed:{err}")
        vms = []

    try:
        disks = disk_collector.collect()
    except AzureDiskCollectionError as err:
        logger.warning("azure.focus_mapper: disk collection failed: %s", err)
        warnings.append(f"disk_collection_failed:{err}")
        disks = []

    try:
        daily_costs: list[AzureResourceDailyCost] = cost_collector.collect_daily_costs(days=30)
    except AzureCostCollectionError as err:
        logger.warning("azure.focus_mapper: cost collection failed: %s", err)
        warnings.append(f"cost_collection_failed:{err}")
        daily_costs = []

    resources: list[Any] = [*vms, *disks]

    if not resources and not daily_costs:
        return FocusDataset(
            tenant_id=tenant_id,
            provider="azure",
            account_id=account_id,
            granularity="daily",
            source="synthesized",
            row_count=0,
            records=[],
            warnings=warnings or ["empty_azure_collection"],
        )

    costs_by_resource: dict[str, list[AzureResourceDailyCost]] = defaultdict(list)
    for cost in daily_costs:
        costs_by_resource[cost.resource_id].append(cost)

    records: list[FocusRecord] = []
    row_index = 0

    for resource in resources:
        service_name, service_category = _service_fields(resource.resource_type)
        resource_costs = costs_by_resource.get(resource.resource_id, [])

        if resource_costs:
            for cost in resource_costs:
                charge_start = datetime(
                    cost.usage_date.year, cost.usage_date.month, cost.usage_date.day, tzinfo=timezone.utc
                )
                charge_end = charge_start + timedelta(days=1)
                billing_start, billing_end = _billing_period_bounds(charge_start)

                raw = {
                    "BillingAccountId": account_id,
                    "BillingPeriodStart": billing_start,
                    "BillingPeriodEnd": billing_end,
                    "ChargePeriodStart": charge_start,
                    "ChargePeriodEnd": charge_end,
                    "ChargeCategory": "Usage",
                    "ChargeDescription": f"Azure Cost Management ActualCost for {resource.resource_id}",
                    "ChargeFrequency": "Usage-Based",
                    "BilledCost": cost.cost,
                    "EffectiveCost": cost.cost,
                    "BillingCurrency": cost.currency,
                    "ProviderName": "Microsoft",
                    "PublisherName": "Microsoft",
                    "RegionId": resource.region,
                    "ResourceId": resource.resource_id,
                    "ResourceName": resource.name,
                    "ResourceType": resource.resource_type,
                    "ServiceCategory": service_category,
                    "ServiceName": service_name,
                    "SkuId": resource.instance_type,
                    "Tags": resource.tags,
                    "extensions": {
                        "x_allocation_method": "cost_management_actual_cost_per_resource",
                        "x_resource_group": resource.resource_group,
                        # "running"/"stopped" for VMs, "unattached"/"attached"
                        # for disks — lets the Analyzer's unattached-storage
                        # rule (Phase 3) work without AWS-specific ID
                        # string matching.
                        "x_resource_state": resource.state,
                    },
                }
                record, row_warnings = FocusRecord.from_raw(raw)
                warnings.extend(f"{w}:row_{row_index}" for w in row_warnings)
                records.append(record)
                row_index += 1
        else:
            # Resource exists but Cost Management has no rows for it yet —
            # new subscriptions can take 24-48h before cost data appears.
            # Still surface the resource, at $0, rather than dropping it.
            now = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
            billing_start, billing_end = _billing_period_bounds(now)
            raw = {
                "BillingAccountId": account_id,
                "BillingPeriodStart": billing_start,
                "BillingPeriodEnd": billing_end,
                "ChargePeriodStart": now,
                "ChargePeriodEnd": now + timedelta(days=1),
                "ChargeCategory": "Usage",
                "ChargeDescription": f"No Cost Management data available yet for {resource.resource_id}",
                "BilledCost": 0,
                "EffectiveCost": 0,
                "BillingCurrency": "USD",
                "ProviderName": "Microsoft",
                "PublisherName": "Microsoft",
                "RegionId": resource.region,
                "ResourceId": resource.resource_id,
                "ResourceName": resource.name,
                "ResourceType": resource.resource_type,
                "ServiceCategory": service_category,
                "ServiceName": service_name,
                "SkuId": resource.instance_type,
                "Tags": resource.tags,
                "extensions": {
                    "x_allocation_method": "no_cost_data_available_yet",
                    "x_resource_state": resource.state,
                },
            }
            warnings.append(f"no_cost_data_available_for_resource:row_{row_index}")
            record, row_warnings = FocusRecord.from_raw(raw)
            warnings.extend(f"{w}:row_{row_index}" for w in row_warnings)
            records.append(record)
            row_index += 1

    logger.info(
        "azure.focus_mapper: synthesized %d FOCUS rows for tenant=%s account=%s "
        "(%d resources, %d resource-cost rows, %d warnings)",
        len(records), tenant_id, account_id, len(resources), len(daily_costs), len(warnings),
    )

    return FocusDataset(
        tenant_id=tenant_id,
        provider="azure",
        account_id=account_id,
        granularity="daily",
        source="synthesized",
        row_count=len(records),
        records=records,
        warnings=warnings,
    )


def _read_focus_export(
    tenant_id: str,
    account_id: str,
    client_factory: AzureClientFactory,
    storage_account: str,
    container: str,
) -> FocusDataset | None:
    """
    Read the most recent Cost Management FOCUS 1.0 export blob from
    https://{storage_account}.blob.core.windows.net/{container}/. Returns
    None — never raises — if not configured, unreadable, or empty, so the
    caller always has a safe fallback to synthesis.
    """
    if not storage_account or not container:
        return None

    try:
        from azure.storage.blob import ContainerClient
    except ImportError:
        logger.warning(
            "azure.focus_mapper: azure-storage-blob not installed, skipping the real "
            "FOCUS export path and falling back to synthesis"
        )
        return None

    try:
        account_url = f"https://{storage_account}.blob.core.windows.net"
        container_client = ContainerClient(
            account_url=account_url, container_name=container, credential=client_factory.credential()
        )

        blobs = [b for b in container_client.list_blobs() if b.name.endswith((".csv", ".csv.gz"))]
        if not blobs:
            logger.info(
                "azure.focus_mapper: no FOCUS export blobs found in %s/%s", storage_account, container
            )
            return None

        latest = max(blobs, key=lambda b: b.last_modified)
        logger.info("azure.focus_mapper: reading live FOCUS export blob %s", latest.name)

        body = container_client.download_blob(latest.name).readall()
        raw_bytes = gzip.decompress(body) if latest.name.endswith(".gz") else body
        rows = list(csv.DictReader(io.StringIO(raw_bytes.decode("utf-8"))))

        records: list[FocusRecord] = []
        warnings: list[str] = []
        for i, row in enumerate(rows):
            record, row_warnings = FocusRecord.from_raw(row)
            warnings.extend(f"{w}:row_{i}" for w in row_warnings)
            records.append(record)

        return FocusDataset(
            tenant_id=tenant_id,
            provider="azure",
            account_id=account_id,
            granularity="daily",
            source="live_export",
            row_count=len(records),
            records=records,
            warnings=warnings,
        )

    except Exception as exc:  # noqa: BLE001 - any storage/parse failure falls back to synthesis
        logger.info("azure.focus_mapper: live_export read failed (%s), falling back to synthesis", exc)
        return None


def map_account_to_focus(
    tenant_id: str,
    account_id: str,
    client_factory: AzureClientFactory,
    focus_storage_account: str = "",
    focus_container: str = "",
) -> FocusDataset:
    """
    Map a connected Azure subscription into a FocusDataset. Tries the real
    Cost Management FOCUS export first (if configured); falls back to
    synthesizing rows from the VM/disk/cost collectors otherwise.
    """
    live = _read_focus_export(tenant_id, account_id, client_factory, focus_storage_account, focus_container)
    if live is not None:
        return live

    return _synthesize_from_collectors(tenant_id, account_id, client_factory)
