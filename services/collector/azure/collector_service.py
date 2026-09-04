"""
Orchestrates the Azure VM + disk + metrics + cost collectors into one
CloudSnapshot, mirroring services/collector/collector_service.py's
AWSCollectorService.

Two things differ from AWS's shape, both deliberate:
  - cpu_metrics stays empty on the returned CloudSnapshot. Azure telemetry
    (services/collector/azure/metrics_collector.py) writes ResourceMetric
    rows straight to the `resource_metrics` collection instead — that's the
    FOCUS-era home for telemetry (services/focus/metrics.py), and
    CloudSnapshot.cpu_metrics is typed for AWS's older EC2CpuMetric shape.
    collect_snapshot_and_metrics() returns the ResourceMetric list
    alongside the snapshot so the caller can persist both.
  - daily_costs stays empty too — Azure Cost Management costs are
    per-resource (packages/schemas/cloud_metrics.py:AzureResourceDailyCost),
    not the account-level DailyCost AWS's Cost Explorer returns, and they
    flow directly into services/focus/mappers/azure.py rather than through
    this AWS-shaped field.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from packages.azure.session import AzureClientFactory
from packages.schemas.cloud_snapshot import CloudSnapshot, CollectionIssue
from services.collector.azure.cost_collector import AzureCostCollectionError, AzureCostCollector
from services.collector.azure.disk_collector import AzureDiskCollectionError, AzureDiskCollector
from services.collector.azure.metrics_collector import AzureMetricsCollector
from services.collector.azure.vm_collector import AzureVMCollectionError, AzureVMCollector
from services.focus.metrics import ResourceMetric


class AzureCollectorService:
    def __init__(
        self,
        client_factory: AzureClientFactory,
        subscription_id: str,
        tenant_id: str,
    ) -> None:
        self.client_factory = client_factory
        self.subscription_id = subscription_id
        self.tenant_id = tenant_id

    def collect_snapshot_and_metrics(self) -> tuple[CloudSnapshot, list[ResourceMetric]]:
        resources: list[dict[str, Any]] = []
        issues: list[CollectionIssue] = []
        metrics: list[ResourceMetric] = []

        vm_succeeded = False
        try:
            vms = AzureVMCollector(self.client_factory).collect()
            resources.extend(vm.model_dump(mode="python") for vm in vms)
            vm_succeeded = True
        except AzureVMCollectionError as error:
            issues.append(
                CollectionIssue(source="azure_vm", error_type=type(error).__name__, message=str(error)[:300])
            )

        try:
            disks = AzureDiskCollector(self.client_factory).collect()
            resources.extend(disk.model_dump(mode="python") for disk in disks)
        except AzureDiskCollectionError as error:
            issues.append(
                CollectionIssue(source="azure_disk", error_type=type(error).__name__, message=str(error)[:300])
            )

        if vm_succeeded:
            try:
                resource_ids = [r["resource_id"] for r in resources if r.get("resource_id")]
                metrics = AzureMetricsCollector(self.client_factory, self.tenant_id).collect_resource_metrics(
                    resource_ids
                )
            except Exception as error:  # noqa: BLE001 - metrics are best-effort, never abort the snapshot
                issues.append(
                    CollectionIssue(
                        source="azure_monitor", error_type=type(error).__name__, message=str(error)[:300]
                    )
                )
        else:
            issues.append(
                CollectionIssue(
                    source="azure_monitor",
                    error_type="DependencyError",
                    message="Metrics collection skipped because VM inventory collection failed.",
                )
            )

        cost_day_count = 0
        try:
            costs = AzureCostCollector(self.client_factory).collect_daily_costs(days=30)
            cost_day_count = len(costs)
        except AzureCostCollectionError as error:
            issues.append(
                CollectionIssue(
                    source="azure_cost_management", error_type=type(error).__name__, message=str(error)[:300]
                )
            )

        if not issues:
            status = "success"
        elif resources:
            status = "partial"
        else:
            status = "failed"

        snapshot = CloudSnapshot(
            account_id=self.subscription_id,
            # Azure resources each carry their own region (see location on
            # every resource dict) — a subscription has no single region.
            region="global",
            collected_at=datetime.now(timezone.utc),
            status=status,
            resource_count=len(resources),
            metric_count=len(metrics),
            cost_day_count=cost_day_count,
            resources=resources,
            cpu_metrics=[],
            daily_costs=[],
            issues=issues,
        )

        return snapshot, metrics
