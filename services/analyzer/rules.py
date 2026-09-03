from __future__ import annotations

import math

from services.analyzer.models import EBSVolume, Finding, MetricSample


OFF_HOURS = set(range(0, 8)) | set(range(18, 24))


def percentile(values: list[float], pct: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    k = (len(ordered) - 1) * (pct / 100)
    lower = int(k)
    upper = min(lower + 1, len(ordered) - 1)
    if lower == upper:
        return ordered[lower]
    return ordered[lower] + (ordered[upper] - ordered[lower]) * (k - lower)


def is_excluded(tags: dict[str, str]) -> bool:
    return str(tags.get("cloudcare:exclude", "")).lower() == "true"


def classify_idle(metrics: list[MetricSample], tags: dict[str, str]) -> Finding | None:
    if is_excluded(tags) or len(metrics) < 7:
        return None

    cpu_p95 = percentile([m.cpu for m in metrics], 95)
    net_p95 = percentile([m.network_bytes for m in metrics], 95)

    if cpu_p95 < 5.0 and net_p95 < 10_000_000:
        return Finding(
            rule_id="ec2.idle.v1",
            severity="medium",
            confidence=0.92,
            evidence={
                "cpu_p95": round(cpu_p95, 3),
                "network_p95_bytes": round(net_p95, 3),
                "window_samples": len(metrics),
            },
        )
    return None


def classify_over_provisioned(metrics: list[MetricSample], tags: dict[str, str]) -> Finding | None:
    if is_excluded(tags) or len(metrics) < 14:
        return None

    memory_values = [m.memory_used_pct for m in metrics if m.memory_used_pct is not None]
    if len(memory_values) < 7:
        return None

    cpu_p95 = percentile([m.cpu for m in metrics], 95)
    memory_p95 = percentile(memory_values, 95)
    memory_headroom_pct = 100.0 - memory_p95

    if cpu_p95 < 25.0 and memory_headroom_pct > 50.0:
        return Finding(
            rule_id="ec2.overprovisioned.v1",
            severity="low",
            confidence=0.80,
            evidence={
                "cpu_p95": round(cpu_p95, 3),
                "memory_used_p95": round(memory_p95, 3),
                "memory_headroom_pct": round(memory_headroom_pct, 3),
                "window_samples": len(metrics),
            },
        )
    return None


def classify_unattached_ebs(volume: EBSVolume, tags: dict[str, str]) -> Finding | None:
    if is_excluded(tags) or volume.state != "available":
        return None
    if volume.unattached_hours is not None and volume.unattached_hours < 24:
        return None

    return Finding(
        rule_id="ebs.unattached.v1",
        severity="low",
        confidence=0.95,
        evidence={
            "volume_id": volume.volume_id,
            "state": volume.state,
            "unattached_hours": volume.unattached_hours,
            "minimum_window_hours": 24,
            "window_hours": 24,
        },
    )


def classify_nonprod_schedule(
    metrics: list[MetricSample],
    tags: dict[str, str],
    environment: str,
) -> Finding | None:
    if is_excluded(tags) or environment.lower() == "prod" or len(metrics) < 14:
        return None

    off_hour_cpus = [m.cpu for m in metrics if m.hour in OFF_HOURS]
    if not off_hour_cpus:
        return None

    off_hours_cpu_p95 = percentile(off_hour_cpus, 95)
    if off_hours_cpu_p95 <= 2.0:
        return Finding(
            rule_id="ec2.nonprod_schedule.v1",
            severity="low",
            confidence=0.85,
            evidence={
                "environment": environment,
                "off_hours_cpu_p95": round(off_hours_cpu_p95, 3),
                "window_samples": len(metrics),
            },
        )
    return None


def classify_spend_anomaly(daily_costs: list[float]) -> Finding | None:
    if len(daily_costs) < 15:
        return None

    baseline = daily_costs[-15:-1]
    current = daily_costs[-1]
    mean = sum(baseline) / len(baseline)
    variance = sum((value - mean) ** 2 for value in baseline) / len(baseline)
    std = math.sqrt(variance)

    if std < 0.01:
        if mean > 0 and current > mean * 3:
            return Finding(
                rule_id="cost.anomaly.v1",
                severity="high",
                confidence=0.90,
                evidence={
                    "current_day_usd": round(current, 4),
                    "baseline_mean_usd": round(mean, 4),
                    "baseline_std_usd": 0.0,
                    "z_score": None,
                    "window_days": 14,
                },
            )
        return None

    z_score = (current - mean) / std
    if z_score > 2.0:
        return Finding(
            rule_id="cost.anomaly.v1",
            severity="high",
            confidence=min(0.5 + z_score * 0.1, 0.99),
            evidence={
                "current_day_usd": round(current, 4),
                "baseline_mean_usd": round(mean, 4),
                "baseline_std_usd": round(std, 4),
                "z_score": round(z_score, 3),
                "window_days": 14,
            },
        )
    return None
