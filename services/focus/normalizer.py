"""
The FOCUS 1.0 normalization engine (spec section 3).

Raw billing telemetry is chaotic by provider — AWS Unblended Costs keyed by
instance id, GCP costs keyed by SubAccountId/project, Azure PreTax Costs
keyed by subscription — this module is the *only* place that reconciles
those shapes into the canonical `UnifiedResource` (packages/schemas/
unified_resource.py). Every adapter calls exactly one `normalize_*`
function per raw resource; nothing downstream ever sees a provider-specific
field name again.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

from packages.schemas.unified_resource import UnifiedResource

_PERIOD_END = datetime.now(timezone.utc)
_PERIOD_START = _PERIOD_END - timedelta(days=1)


def _service_category(resource_type: str) -> str:
    resource_type = resource_type.lower()
    if any(k in resource_type for k in ("instance", "vm", "compute", "ec2")):
        return "Compute"
    if any(k in resource_type for k in ("disk", "volume", "storage", "blob", "bucket")):
        return "Storage"
    if any(k in resource_type for k in ("sql", "db", "database")):
        return "Database"
    if any(k in resource_type for k in ("network", "load_balancer", "vpc")):
        return "Networking"
    return "Other"


def normalize_aws(resource: dict[str, Any], daily_cost_usd: float | None = None) -> UnifiedResource:
    """AWS: `UnblendedCost` -> effective_cost; on-demand list price approximated
    by billed_cost when no reservation/savings-plan discount data is present."""
    resource_type = resource.get("resource_type", "ec2_instance")
    cost = float(daily_cost_usd if daily_cost_usd is not None else resource.get("monthly_cost_usd", 0.0) / 30)

    return UnifiedResource(
        id=resource.get("resource_id") or resource.get("instance_id", "unknown"),
        provider="aws",
        account_id=resource.get("account_id", "000000000000"),
        resource_name=resource.get("name"),
        resource_type=resource_type,
        service_category=_service_category(resource_type),  # type: ignore[arg-type]
        service_name="Amazon EC2" if "instance" in resource_type else "Amazon EBS",
        region=resource.get("region", "us-east-1"),
        availability_zone=resource.get("availability_zone"),
        billed_cost=cost,
        effective_cost=cost,
        list_cost=cost,
        charge_category="Usage",
        billing_period_start=_PERIOD_START,
        billing_period_end=_PERIOD_END,
        state=resource.get("state", "unknown"),
        environment=str(resource.get("environment", "unknown")).lower(),
        metrics_cpu_utilization_p95=resource.get("cpu_p95"),
        metrics_memory_utilization_p95=resource.get("memory_p95"),
        metrics_network_bytes_p95=resource.get("network_p95"),
        metrics_cpu_samples=resource.get("cpu_samples", []),
        metrics_network_bytes_samples=resource.get("network_samples", []),
        tags=resource.get("tags", {}),
        owner=resource.get("tags", {}).get("Owner") or resource.get("owner"),
    )


def normalize_gcp(resource: dict[str, Any]) -> UnifiedResource:
    """GCP: `SubAccountId` (project) -> account_id, `PreTaxCostUsd` -> billed_cost,
    labels -> tags (GCP has no native tag/label distinction like AWS)."""
    return UnifiedResource(
        id=resource["resource_id"],
        provider="gcp",
        account_id=resource.get("sub_account_id", "unknown-project"),
        resource_name=resource.get("name"),
        resource_type=resource.get("machine_type", "compute_instance"),
        service_category=_service_category(resource.get("resource_kind", "compute")),  # type: ignore[arg-type]
        service_name="Compute Engine",
        region=resource.get("zone", "us-central1-a").rsplit("-", 1)[0],
        availability_zone=resource.get("zone"),
        billed_cost=float(resource.get("pretax_cost_usd", 0.0)),
        effective_cost=float(resource.get("pretax_cost_usd", 0.0)) * (1 - float(resource.get("discount_pct", 0.0))),
        list_cost=float(resource.get("list_cost_usd", resource.get("pretax_cost_usd", 0.0))),
        charge_category="Usage",
        billing_period_start=_PERIOD_START,
        billing_period_end=_PERIOD_END,
        state=resource.get("status", "unknown").lower(),
        environment=str(resource.get("labels", {}).get("env", "unknown")).lower(),
        metrics_cpu_utilization_p95=resource.get("cpu_utilization_p95"),
        metrics_memory_utilization_p95=resource.get("memory_utilization_p95"),
        metrics_network_bytes_p95=resource.get("network_bytes_p95"),
        metrics_cpu_samples=resource.get("cpu_samples", []),
        metrics_network_bytes_samples=resource.get("network_samples", []),
        tags=resource.get("labels", {}),
        owner=resource.get("labels", {}).get("owner"),
    )


def normalize_azure(resource: dict[str, Any]) -> UnifiedResource:
    """Azure: `subscriptionId` -> account_id, `preTaxCost` -> billed_cost,
    `powerState` -> state."""
    return UnifiedResource(
        id=resource["resource_id"],
        provider="azure",
        account_id=resource.get("subscription_id", "unknown-subscription"),
        resource_name=resource.get("name"),
        resource_type=resource.get("vm_size", "virtual_machine"),
        service_category=_service_category(resource.get("resource_kind", "compute")),  # type: ignore[arg-type]
        service_name="Azure Virtual Machines",
        region=resource.get("location", "eastus"),
        availability_zone=resource.get("zone"),
        billed_cost=float(resource.get("pre_tax_cost", 0.0)),
        effective_cost=float(resource.get("pre_tax_cost", 0.0)),
        list_cost=float(resource.get("list_cost", resource.get("pre_tax_cost", 0.0))),
        charge_category="Usage",
        billing_period_start=_PERIOD_START,
        billing_period_end=_PERIOD_END,
        state=str(resource.get("power_state", "unknown")).lower(),
        environment=str(resource.get("tags", {}).get("environment", "unknown")).lower(),
        metrics_cpu_utilization_p95=resource.get("cpu_percentile_95"),
        metrics_memory_utilization_p95=resource.get("memory_percentile_95"),
        metrics_network_bytes_p95=resource.get("network_bytes_p95"),
        metrics_cpu_samples=resource.get("cpu_samples", []),
        metrics_network_bytes_samples=resource.get("network_samples", []),
        tags=resource.get("tags", {}),
        owner=resource.get("tags", {}).get("owner"),
    )


def normalize_onprem(resource: dict[str, Any]) -> UnifiedResource:
    """Simulated on-prem/VPS fleet: no cloud billing API exists, so
    `monthly_hosting_cost_usd` (a flat colo/VPS invoice line) stands in for
    billed/effective/list cost — there's no usage-based discount to model."""
    cost = float(resource.get("monthly_hosting_cost_usd", 0.0)) / 30
    return UnifiedResource(
        id=resource["host_id"],
        provider="onprem",
        account_id=resource.get("datacenter", "dc-1"),
        resource_name=resource.get("hostname"),
        resource_type="vps",
        service_category="Compute",
        service_name="On-Prem VPS",
        region=resource.get("datacenter", "dc-1"),
        billed_cost=cost,
        effective_cost=cost,
        list_cost=cost,
        charge_category="Usage",
        billing_period_start=_PERIOD_START,
        billing_period_end=_PERIOD_END,
        state="running",
        environment=str(resource.get("environment", "prod")).lower(),
        metrics_cpu_utilization_p95=resource.get("cpu_util_p95"),
        metrics_memory_utilization_p95=resource.get("mem_util_p95"),
        metrics_cpu_samples=resource.get("cpu_samples", []),
        metrics_network_bytes_samples=resource.get("network_samples", []),
        tags=resource.get("tags", {}),
        owner=resource.get("owner"),
    )
