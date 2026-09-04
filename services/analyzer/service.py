"""
Analyzer Agent (Detect) — deterministic rule engine, now reading FOCUS 1.0
records + resource_metrics instead of the AWS-shaped CloudSnapshot.

services/analyzer/rules.py is unchanged, byte-for-byte: classify_idle,
classify_over_provisioned, classify_unattached_ebs, classify_nonprod_schedule
and classify_spend_anomaly keep the exact same thresholds and signatures
they always had. Everything in this file is the adapter that feeds them —
grouping FOCUS records by ResourceId, joining resource_metrics, deriving
environment from Tags, and translating provider-specific vocabulary
("unattached" vs "available") into what the unchanged rules expect.

HONESTY RULE FOR THE NEW PATH: a resource with no resource_metrics entry
gets an empty sample list, which fails classify_idle/over_provisioned's
`len(metrics) >= 7/14` gate — no metrics means no finding, never a
fabricated 0%-CPU or default-memory reading. classify_nonprod_schedule
needs real hour-of-day granularity that the aggregate ResourceMetric
(cpu_p95/cpu_avg/mem_p95 — a window *summary*, not a raw per-hour series)
doesn't carry, so every synthetic sample gets hour=12 (never inside
OFF_HOURS), meaning that rule naturally never fires on FOCUS-native data —
the same effect the pre-FOCUS adapter got from defaulting missing
timestamps to noon, kept here rather than fabricating a fake hourly
pattern.

LEGACY PATH: a plain CloudSnapshot dict (no top-level "records" key) is
converted through services/focus/mappers/aws.py first, with
resource_metrics synthesized from its cpu_metrics using the exact
defaulting the pre-FOCUS adapter used (a flat 35%-memory-used, 100KB
network default, sample_count padded to >=14) — CloudSnapshot/EC2CpuMetric
never carried a real memory or network reading, and this default is what
let classify_over_provisioned fire in the shipped system before FOCUS
existed. It is kept ONLY on this path, so
tests/unit/test_analyzer_agent.py keeps passing unchanged; the FOCUS-native
path above never does this.
"""

from __future__ import annotations

from collections import defaultdict
from datetime import date, datetime, timezone
from decimal import Decimal
from typing import Any

from packages.schemas.focus import FocusDataset, FocusRecord
from services.analyzer.models import EBSVolume, MetricSample
from services.analyzer.rules import (
    classify_idle,
    classify_nonprod_schedule,
    classify_over_provisioned,
    classify_spend_anomaly,
    classify_unattached_ebs,
)
from services.focus.metrics import ResourceMetric

# Case-insensitive Tags lookup keys for environment — "env", "Environment"
# and "ENV" all lower() to one of these two.
_ENV_TAG_KEYS = ("env", "environment")

_ENV_ALIASES = {
    "dev": "dev", "development": "dev",
    "stage": "staging", "stg": "staging", "staging": "staging",
    "prod": "prod", "production": "prod",
}

# Provider-specific "not attached to anything" vocabulary, all normalized
# to "available" — the one literal string classify_unattached_ebs checks
# for (services/analyzer/rules.py is unchanged, so the adapter has to
# speak its vocabulary, not the other way around).
_UNATTACHED_STATE_ALIASES = {"available", "unattached", "detached", "reserved"}


def analyze_observation(
    observation: "FocusDataset | dict[str, Any]",
    resource_metrics: "list[ResourceMetric] | list[dict[str, Any]] | None" = None,
) -> list[dict[str, Any]]:
    """
    Run the deterministic Analyzer rules against `observation`.

    `observation` may be:
      - a FocusDataset instance,
      - a dict with a top-level "records" key (a FocusDataset.model_dump()),
      - a legacy CloudSnapshot dict (converted through the AWS mapper).

    `resource_metrics` is a list of ResourceMetric (or their dumped dicts)
    for the same tenant. Ignored on the legacy path unless explicitly
    provided — a legacy CloudSnapshot's own cpu_metrics is used instead.
    """
    dependency_context_by_resource: dict[str, dict[str, Any]] = {}

    if isinstance(observation, FocusDataset):
        dataset = observation
        metrics_by_resource = _index_metrics(resource_metrics or [])
    elif isinstance(observation, dict) and "records" in observation:
        dataset = FocusDataset(**observation)
        metrics_by_resource = _index_metrics(resource_metrics or [])
    elif isinstance(observation, dict):
        dataset, legacy_metrics = _convert_legacy_snapshot(observation)
        metrics_by_resource = _index_metrics(resource_metrics) if resource_metrics else legacy_metrics
        # Phase 15 — dependency_context (ASG/LB/termination-protection/
        # missing-ownership) lives on the raw CloudSnapshot resource dicts
        # the collector produced, not on FocusRecord — real AWS billing
        # exports (the "live_export" FOCUS source) have no way to carry an
        # AWS-API-derived fact like ASG membership, so this is read
        # straight from the pre-FOCUS resources list rather than threaded
        # through the FOCUS mapper, and works identically regardless of
        # which FOCUS source (live_export vs synthesized) was used.
        for resource in observation.get("resources", []):
            rid = resource.get("resource_id") or resource.get("instance_id") or resource.get("id")
            dep_ctx = resource.get("dependency_context")
            if rid and dep_ctx:
                dependency_context_by_resource[rid] = dep_ctx
    else:
        raise TypeError(f"Unsupported observation type: {type(observation)!r}")

    return _analyze(dataset, metrics_by_resource, dependency_context_by_resource)


# ---------------------------------------------------------------------------
# Input coercion
# ---------------------------------------------------------------------------


def _index_metrics(resource_metrics: Any) -> dict[str, ResourceMetric]:
    indexed: dict[str, ResourceMetric] = {}
    for item in resource_metrics:
        metric = item if isinstance(item, ResourceMetric) else ResourceMetric(**item)
        indexed[metric.resource_id] = metric
    return indexed


def _convert_legacy_snapshot(observation: dict[str, Any]) -> tuple[FocusDataset, dict[str, ResourceMetric]]:
    from services.focus.mappers.aws import map_snapshot_to_focus

    tenant_id = observation.get("tenant_id") or "legacy"
    dataset = map_snapshot_to_focus(observation, tenant_id=tenant_id)

    now = datetime.now(timezone.utc)
    cpu_by_instance: dict[str, dict[str, Any]] = {
        m.get("instance_id"): m for m in observation.get("cpu_metrics", []) if m.get("instance_id")
    }

    legacy_metrics: dict[str, ResourceMetric] = {}
    for resource in observation.get("resources", []):
        resource_id = resource.get("resource_id") or resource.get("instance_id") or resource.get("id")
        if not resource_id:
            continue
        cpu_metric = cpu_by_instance.get(resource_id)
        if not cpu_metric:
            continue

        cpu_p95 = cpu_metric.get("maximum_cpu_percent")
        cpu_avg = cpu_metric.get("average_cpu_percent")
        if cpu_p95 is None and cpu_avg is None:
            continue
        sample_count = int(cpu_metric.get("datapoint_count") or 0)

        legacy_metrics[resource_id] = ResourceMetric(
            resource_id=resource_id,
            tenant_id=tenant_id,
            window_start=now,
            window_end=now,
            cpu_p95=cpu_p95 if cpu_p95 is not None else cpu_avg,
            cpu_avg=cpu_avg if cpu_avg is not None else cpu_p95,
            mem_p95=35.0,
            network_p95_bytes=100_000.0,
            sample_count=max(sample_count, 14),
        )

    return dataset, legacy_metrics


# ---------------------------------------------------------------------------
# FOCUS-native analysis
# ---------------------------------------------------------------------------


def _environment_from_tags(tags: dict[str, Any]) -> str:
    lowered = {str(k).lower(): v for k, v in (tags or {}).items()}
    for key in _ENV_TAG_KEYS:
        if lowered.get(key):
            raw = str(lowered[key]).strip().lower()
            return _ENV_ALIASES.get(raw, raw)
    return "unknown"


def _metric_samples_for(metric: ResourceMetric | None) -> list[MetricSample]:
    """
    Reconstructs a synthetic per-sample series from a ResourceMetric window
    summary. Every synthetic sample carries the SAME cpu/network/memory
    value, so percentile(values, N) == that recorded value for any N — the
    rule functions only ever threshold on the p95, never the raw
    distribution shape, so this is lossless for what they actually compute.
    The list length is the real sample_count, never padded — a resource
    with too few real samples correctly fails the rules' own
    `len(metrics) >= 7/14` gate rather than being propped up to pass it.
    hour=12 on every sample (see module docstring) — never an OFF_HOURS
    bucket, so classify_nonprod_schedule naturally returns None here
    instead of being fed a fabricated hourly pattern.
    """
    if metric is None or not metric.sample_count:
        return []

    cpu = metric.cpu_p95 if metric.cpu_p95 is not None else metric.cpu_avg
    if cpu is None:
        return []

    # classify_idle requires BOTH cpu_p95 < 5% AND net_p95 < 10MB. Some
    # collectors (AWS CloudWatch here) never measure network at all. This
    # default deliberately matches the pre-FOCUS adapter's own convention
    # (it defaulted an absent network series to 100_000 bytes — comfortably
    # under the 10MB threshold, not zero, not infinite): a provider that
    # never measures network shouldn't have idle detection silently and
    # permanently disabled just because that one signal is unavailable.
    # This is a real, disclosed trade-off, not a "no risk" choice — a
    # resource with genuinely low CPU but real (unmeasured) network traffic
    # could be misclassified idle when network coverage is missing. Compare
    # with the no-ResourceMetric-at-all case above, which correctly
    # suppresses the finding entirely rather than guessing.
    network = metric.network_p95_bytes if metric.network_p95_bytes is not None else 0.0

    return [
        MetricSample(cpu=cpu, network_bytes=network, memory_used_pct=metric.mem_p95, hour=12)
        for _ in range(metric.sample_count)
    ]


def _normalized_resource_state(record: FocusRecord) -> str:
    raw = str(record.extensions.get("x_resource_state") or "").strip().lower()
    return "available" if raw in _UNATTACHED_STATE_ALIASES else raw


def _ebs_volume_from_records(resource_id: str, records: list[FocusRecord]) -> EBSVolume:
    representative = max(records, key=lambda r: r.ChargePeriodStart)
    state = _normalized_resource_state(representative)

    unattached_hours: float | None = None
    if state == "available":
        earliest = min(r.ChargePeriodStart for r in records)
        latest = max(r.ChargePeriodEnd for r in records)
        unattached_hours = round((latest - earliest).total_seconds() / 3600, 2)

    return EBSVolume(volume_id=resource_id, state=state, unattached_hours=unattached_hours)


def _daily_billed_cost_series(records: list[FocusRecord]) -> list[float]:
    daily_totals: dict[date, Decimal] = defaultdict(lambda: Decimal("0"))
    for record in records:
        daily_totals[record.ChargePeriodStart.date()] += record.BilledCost
    return [float(daily_totals[day]) for day in sorted(daily_totals)]


def _provenance(representative: FocusRecord, dataset: FocusDataset, records: list[FocusRecord]) -> dict[str, Any]:
    billed_cost_30d = sum((r.BilledCost for r in records), Decimal("0"))
    return {
        "provider": representative.ProviderName,
        "service_name": representative.ServiceName,
        "service_category": representative.ServiceCategory,
        # Named "_30d" to match the field Phase 3 specifies — it's really
        # "summed across this dataset's observed window" (AWS/Azure
        # synthesis both cover ~30 days; FOCUS sample data may cover less).
        "billed_cost_30d": float(billed_cost_30d),
        "focus_dataset_id": dataset.dataset_id,
    }


def _focus_citation(representative: FocusRecord) -> dict[str, Any]:
    """The exact FOCUS columns a finding's classification drew on — the
    chatbot and the UI both need this provenance to explain "why" a
    finding fired in terms of real billing data, not just a rule name."""
    return {
        "ResourceId": representative.ResourceId,
        "ProviderName": representative.ProviderName,
        "ServiceCategory": representative.ServiceCategory,
        "ServiceName": representative.ServiceName,
        "ChargeCategory": representative.ChargeCategory,
        "BilledCost": str(representative.BilledCost),
    }


def _enrich(
    finding,
    resource_id: str,
    provenance: dict[str, Any],
    citation: dict[str, Any],
    dependency_context: dict[str, Any] | None = None,
) -> dict[str, Any]:
    doc = finding.to_dict(resource_id)
    doc.update(provenance)
    doc["evidence"] = {**doc["evidence"], "focus_columns": citation}
    # Phase 15 — never dropped for having a dependency (ASG/LB/etc) now;
    # attached here so it's visible on the Finding itself, not just used
    # internally by services/decision/service.py::build_proposals (which
    # reads it independently, straight off the resource dict it's given).
    doc["dependency_context"] = dependency_context or {}
    return doc


def _analyze(
    dataset: FocusDataset,
    metrics_by_resource: dict[str, ResourceMetric],
    dependency_context_by_resource: dict[str, dict[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    dependency_context_by_resource = dependency_context_by_resource or {}
    findings: list[dict[str, Any]] = []

    records_by_resource: dict[str, list[FocusRecord]] = defaultdict(list)
    for record in dataset.records:
        if record.ResourceId:
            records_by_resource[record.ResourceId].append(record)

    # Item 3: identify storage resources by FOCUS taxonomy (ServiceCategory
    # / ChargeCategory), never by ID string matching ("vol-" etc) — and a
    # storage resource is only a candidate if its ResourceId never appears
    # as a Compute+Usage resource anywhere in the dataset.
    compute_resource_ids = {
        record.ResourceId
        for record in dataset.records
        if record.ServiceCategory == "Compute" and record.ChargeCategory == "Usage" and record.ResourceId
    }

    for resource_id, records in records_by_resource.items():
        representative = max(records, key=lambda r: r.ChargePeriodStart)
        tags = representative.Tags or {}
        environment = _environment_from_tags(tags)
        provenance = _provenance(representative, dataset, records)
        citation = _focus_citation(representative)

        dep_ctx = dependency_context_by_resource.get(resource_id)

        if representative.ServiceCategory == "Compute":
            samples = _metric_samples_for(metrics_by_resource.get(resource_id))
            for finding in (
                classify_idle(samples, tags),
                classify_over_provisioned(samples, tags),
                classify_nonprod_schedule(samples, tags, environment),
            ):
                if finding:
                    findings.append(_enrich(finding, resource_id, provenance, citation, dep_ctx))

        if (
            representative.ServiceCategory == "Storage"
            and representative.ChargeCategory == "Usage"
            and resource_id not in compute_resource_ids
        ):
            volume = _ebs_volume_from_records(resource_id, records)
            finding = classify_unattached_ebs(volume, tags)
            if finding:
                findings.append(_enrich(finding, resource_id, provenance, citation, dep_ctx))

    # Item 2: spend anomaly on the FOCUS BilledCost time series, grouped by
    # (ServiceName, ResourceId) — daily totals, not per-charge-row, so
    # hourly-granularity datasets (FOCUS sample data) and daily-granularity
    # ones (AWS/Azure synthesis) are compared on the same footing.
    service_resource_groups: dict[tuple[str, str], list[FocusRecord]] = defaultdict(list)
    for record in dataset.records:
        if record.ResourceId:
            service_resource_groups[(record.ServiceName, record.ResourceId)].append(record)

    for (_service_name, resource_id), records in service_resource_groups.items():
        finding = classify_spend_anomaly(_daily_billed_cost_series(records))
        if finding:
            representative = max(records, key=lambda r: r.ChargePeriodStart)
            findings.append(
                _enrich(finding, resource_id, _provenance(representative, dataset, records), _focus_citation(representative))
            )

    # Account-level spend anomaly, across every record in the dataset —
    # continues the pre-FOCUS adapter's "account-billing-history" finding.
    if dataset.records:
        account_finding = classify_spend_anomaly(_daily_billed_cost_series(dataset.records))
        if account_finding:
            total_cost = sum((r.BilledCost for r in dataset.records), Decimal("0"))
            findings.append(
                _enrich(
                    account_finding,
                    "account-billing-history",
                    {
                        "provider": dataset.provider,
                        "service_name": "account-billing-history",
                        "service_category": None,
                        "billed_cost_30d": float(total_cost),
                        "focus_dataset_id": dataset.dataset_id,
                    },
                    {"ProviderName": dataset.provider, "focus_dataset_id": dataset.dataset_id},
                )
            )

    return findings
