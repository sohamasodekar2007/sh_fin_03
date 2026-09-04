"""
Azure resource metrics collector — queries azure-monitor-query for
"Percentage CPU" and "Available Memory Bytes" over a 14-day window, the
window services/analyzer/rules.py's classify_over_provisioned needs (it
requires >= 14 samples; classify_idle needs >= 7) once Phase 3 rewires the
Analyzer agent onto FOCUS + resource_metrics. Produces ResourceMetric rows
(services/focus/metrics.py) keyed by the full Azure ARM resource ID —
callers persist them via services/focus/metrics.py:save_resource_metrics(),
mirroring how services/collector/cloudwatch_collector.py only collects and
lets its caller decide what to do with the result.

CPU is reported by every VM; "Available Memory Bytes" requires the Azure
guest diagnostics extension — a VM without it simply returns no memory
datapoints. Missing data is never defaulted to 0 (that manufactures false
idle/over-provisioned findings) — a VM with no CPU datapoints at all
(deallocated, or diagnostics never enabled) is skipped entirely rather than
recorded with fabricated zeros.

UNIT NOTE: mem_p95 here is the p95 of *available* memory in bytes (what the
metric actually reports), not a %-used figure — converting to %-used needs
the VM size's total memory looked up separately, which Phase 3 can add when
it actually consumes this field.
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone

from packages.azure.session import AzureClientFactory
from services.focus.metrics import ResourceMetric

logger = logging.getLogger(__name__)

METRIC_NAMES = ["Percentage CPU", "Available Memory Bytes"]
DEFAULT_WINDOW_DAYS = 14


def _percentile(values: list[float], pct: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    k = (len(ordered) - 1) * (pct / 100)
    lower = int(k)
    upper = min(lower + 1, len(ordered) - 1)
    if lower == upper:
        return ordered[lower]
    return ordered[lower] + (ordered[upper] - ordered[lower]) * (k - lower)


class AzureMetricsCollector:
    def __init__(self, client_factory: AzureClientFactory, tenant_id: str) -> None:
        self.client_factory = client_factory
        self.tenant_id = tenant_id

    def collect_resource_metrics(
        self,
        resource_ids: list[str],
        window_days: int = DEFAULT_WINDOW_DAYS,
    ) -> list[ResourceMetric]:
        if window_days < 1:
            raise ValueError("window_days must be at least 1")

        client = self.client_factory.metrics_query_client()
        window_end = datetime.now(timezone.utc)
        window_start = window_end - timedelta(days=window_days)

        collected: list[ResourceMetric] = []

        for resource_id in resource_ids:
            if not resource_id:
                continue

            try:
                result = client.query_resource(
                    resource_id,
                    metric_names=METRIC_NAMES,
                    timespan=(window_start, window_end),
                    granularity=timedelta(hours=1),
                    aggregations=["Average"],
                )
            except Exception as error:  # noqa: BLE001 - one bad resource must not abort the batch
                logger.info("azure.metrics_collector: query failed for %s: %s", resource_id, error)
                continue

            cpu_values: list[float] = []
            mem_values: list[float] = []

            for metric in getattr(result, "metrics", None) or []:
                is_cpu = metric.name == "Percentage CPU"
                is_mem = metric.name == "Available Memory Bytes"
                if not (is_cpu or is_mem):
                    continue
                for series in metric.timeseries:
                    for point in series.data:
                        value = point.average
                        if value is None:
                            continue
                        (cpu_values if is_cpu else mem_values).append(float(value))

            if not cpu_values:
                # Deallocated VM, or diagnostics never enabled — never
                # record a 0%-CPU row for this; just skip it, same as
                # AWS's CloudWatchCollector leaves average_cpu_percent=None.
                continue

            collected.append(
                ResourceMetric(
                    resource_id=resource_id,
                    tenant_id=self.tenant_id,
                    window_start=window_start,
                    window_end=window_end,
                    cpu_p95=round(_percentile(cpu_values, 95), 4),
                    cpu_avg=round(sum(cpu_values) / len(cpu_values), 4),
                    mem_p95=round(_percentile(mem_values, 95), 2) if mem_values else None,
                    network_p95_bytes=None,
                    sample_count=len(cpu_values),
                )
            )

        return collected
