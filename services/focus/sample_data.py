"""
Synthetic multi-cloud data gravity for the Analyzer/Decision/Supervisor
pipeline to chew on before a real GCP/Azure account is connected — mirrors
services/collector/mock_provider.py's AWS generator, in each provider's own
raw shape, so services/focus/normalizer.py has something real to normalize.

PLACEHOLDER for judging: to fuse in the official FOCUS 1.0 sample dataset
(https://focus.finops.org — "FOCUS Sample Data Files") or a real AWS Cost
and Usage Report export, drop the CSV under scripts/data/ and load it with
pandas in scripts/seed_focus_sample.py; each row already lines up with
UnifiedResource's FOCUS-1.0-named columns (BilledCost, EffectiveCost,
ServiceCategory, ...), so it needs a column-rename, not a new parser.
"""

from __future__ import annotations

import random
from typing import Any

_PATTERNS = ["idle", "oversized", "nonprod_schedule", "normal"]


def _cpu_series(pattern: str) -> list[float]:
    if pattern == "idle":
        return [round(random.uniform(0.5, 3.5), 2) for _ in range(14)]
    if pattern == "oversized":
        return [round(random.uniform(6.0, 18.0), 2) for _ in range(14)]
    if pattern == "nonprod_schedule":
        return [round(random.uniform(0.2, 1.8), 2) for _ in range(14)]
    return [round(random.uniform(35.0, 70.0), 2) for _ in range(14)]


def _p95(series: list[float]) -> float:
    ordered = sorted(series)
    return ordered[int(len(ordered) * 0.95) - 1]


def _network_series(pattern: str) -> list[float]:
    base = 2_000_000.0 if pattern in ("idle", "nonprod_schedule") else 50_000_000.0
    return [round(max(0.0, base + random.gauss(0, base * 0.1)), 0) for _ in range(14)]


def generate_gcp_resources(project_id: str = "cloudcare-demo-project", n: int = 12) -> list[dict[str, Any]]:
    random.seed(202)
    zones = ["us-central1-a", "us-central1-b", "europe-west1-b"]
    machine_types = ["e2-medium", "e2-standard-4", "n2-standard-8", "e2-small"]
    resources = []
    for i in range(n):
        pattern = _PATTERNS[i % len(_PATTERNS)]
        cpu = _cpu_series(pattern)
        net = _network_series(pattern)
        resources.append(
            {
                "resource_id": f"gcp-vm-{i:03d}",
                "name": f"cloudcare-gcp-{pattern}-{i:02d}",
                "sub_account_id": project_id,
                "machine_type": machine_types[i % len(machine_types)],
                "resource_kind": "compute_instance",
                "zone": zones[i % len(zones)],
                "status": "running",
                "pretax_cost_usd": round(random.uniform(3.0, 45.0), 2),
                "discount_pct": 0.0,
                "cpu_utilization_p95": _p95(cpu),
                "memory_utilization_p95": round(random.uniform(20.0, 85.0), 2),
                "network_bytes_p95": _p95(net),
                "cpu_samples": cpu,
                "network_samples": net,
                "labels": {"env": "dev" if i % 3 else "prod", "owner": f"team-{i % 4}", "pattern": pattern},
            }
        )
    return resources


def generate_azure_resources(subscription_id: str = "cloudcare-demo-subscription", n: int = 10) -> list[dict[str, Any]]:
    random.seed(303)
    locations = ["eastus", "westeurope", "southeastasia"]
    vm_sizes = ["Standard_B2s", "Standard_D4s_v3", "Standard_E2s_v3"]
    resources = []
    for i in range(n):
        pattern = _PATTERNS[i % len(_PATTERNS)]
        cpu = _cpu_series(pattern)
        net = _network_series(pattern)
        resources.append(
            {
                "resource_id": f"azure-vm-{i:03d}",
                "name": f"cloudcare-az-{pattern}-{i:02d}",
                "subscription_id": subscription_id,
                "vm_size": vm_sizes[i % len(vm_sizes)],
                "resource_kind": "virtual_machine",
                "location": locations[i % len(locations)],
                "power_state": "running",
                "pre_tax_cost": round(random.uniform(4.0, 50.0), 2),
                "cpu_percentile_95": _p95(cpu),
                "memory_percentile_95": round(random.uniform(20.0, 85.0), 2),
                "network_bytes_p95": _p95(net),
                "cpu_samples": cpu,
                "network_samples": net,
                "tags": {"environment": "staging" if i % 2 else "prod", "owner": f"team-{i % 4}", "pattern": pattern},
            }
        )
    return resources


def generate_onprem_resources(datacenter: str = "dc-pune-01", n: int = 6) -> list[dict[str, Any]]:
    random.seed(404)
    resources = []
    for i in range(n):
        pattern = _PATTERNS[i % len(_PATTERNS)]
        cpu = _cpu_series(pattern)
        net = _network_series(pattern)
        resources.append(
            {
                "host_id": f"vps-{i:03d}",
                "hostname": f"onprem-{pattern}-{i:02d}.internal",
                "datacenter": datacenter,
                "cpu_util_p95": _p95(cpu),
                "mem_util_p95": round(random.uniform(20.0, 85.0), 2),
                "monthly_hosting_cost_usd": round(random.uniform(40.0, 220.0), 2),
                "environment": "prod",
                "owner": f"infra-team-{i % 2}",
                "cpu_samples": cpu,
                "network_samples": net,
                "tags": {"pattern": pattern},
            }
        )
    return resources


def daily_cost_series(base: float = 320.0, days: int = 30, anomaly_on_last_day: bool = True) -> list[float]:
    """Shared 30-day cost series generator used by every provider's mock
    adapter to feed services.analyzer.rules.classify_spend_anomaly."""
    random.seed(505)
    series = [round(base + random.uniform(-12.0, 15.0), 2) for _ in range(days)]
    if anomaly_on_last_day:
        series[-1] += 650.0
    return series
