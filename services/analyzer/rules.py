from __future__ import annotations

import math

from services.analyzer.models import EBSVolume, Finding, MetricSample
from services.governance.tags import is_excluded

__all__ = [
    "is_excluded", "classify_idle", "classify_over_provisioned",
    "classify_unattached_ebs", "classify_nonprod_schedule", "classify_spend_anomaly",
    "classify_rds_configuration", "classify_dynamodb_configuration",
    "classify_lambda_configuration", "classify_security_group_ingress",
    "percentile", "OFF_HOURS",
]

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


def classify_rds_configuration(resource: dict) -> list[Finding]:
    tags = resource.get("tags") or {}
    if is_excluded(tags):
        return []

    findings: list[Finding] = []
    resource_id = str(resource.get("resource_id") or "")
    if resource.get("storage_encrypted") is False:
        findings.append(
            Finding(
                rule_id="rds.unencrypted.v1",
                severity="medium",
                confidence=0.96,
                evidence={"storage_encrypted": False, "engine": resource.get("engine")},
            )
        )
    if resource.get("publicly_accessible") is True:
        findings.append(
            Finding(
                rule_id="rds.publicly_accessible.v1",
                severity="critical",
                confidence=0.98,
                evidence={"publicly_accessible": True, "engine": resource.get("engine")},
            )
        )
    if resource.get("multi_az") is False and str(resource.get("state", "")).lower() == "available":
        findings.append(
            Finding(
                rule_id="rds.single_az.v1",
                severity="medium",
                confidence=0.90,
                evidence={"multi_az": False, "state": resource.get("state"), "resource_id": resource_id},
            )
        )
    if resource.get("deletion_protection") is False:
        findings.append(
            Finding(
                rule_id="rds.deletion_protection_disabled.v1",
                severity="medium",
                confidence=0.92,
                evidence={"deletion_protection": False},
            )
        )
    return findings


def classify_dynamodb_configuration(resource: dict) -> list[Finding]:
    tags = resource.get("tags") or {}
    if is_excluded(tags):
        return []
    if resource.get("point_in_time_recovery_enabled") is not False:
        return []
    return [
        Finding(
            rule_id="dynamodb.pitr_disabled.v1",
            severity="medium",
            confidence=0.93,
            evidence={
                "point_in_time_recovery_enabled": False,
                "billing_mode": resource.get("billing_mode") or resource.get("instance_type"),
            },
        )
    ]


def classify_lambda_configuration(resource: dict) -> list[Finding]:
    tags = resource.get("tags") or {}
    if is_excluded(tags):
        return []

    findings: list[Finding] = []
    timeout = resource.get("timeout_seconds")
    try:
        timeout_value = int(timeout) if timeout is not None else None
    except (TypeError, ValueError):
        timeout_value = None
    if timeout_value is not None and timeout_value >= 60:
        findings.append(
            Finding(
                rule_id="lambda.long_timeout.v1",
                severity="low",
                confidence=0.86,
                evidence={"timeout_seconds": timeout_value, "runtime": resource.get("runtime")},
            )
        )
    if resource.get("vpc_config_present") is False and str(resource.get("environment", "")).lower() in {"prod", "production"}:
        findings.append(
            Finding(
                rule_id="lambda.prod_without_vpc.v1",
                severity="medium",
                confidence=0.82,
                evidence={"vpc_config_present": False, "runtime": resource.get("runtime")},
            )
        )
    return findings


_SENSITIVE_INGRESS_PORTS = {22: "SSH", 3389: "RDP", 3306: "MySQL", 5432: "PostgreSQL", 27017: "MongoDB", 6379: "Redis"}
_OPEN_CIDRS = {"0.0.0.0/0", "::/0"}


def classify_security_group_ingress(resource: dict) -> list[Finding]:
    tags = resource.get("tags") or {}
    if is_excluded(tags):
        return []

    findings: list[Finding] = []
    for rule in resource.get("ingress_rules") or []:
        cidr = rule.get("cidr")
        if cidr not in _OPEN_CIDRS:
            continue
        from_port = rule.get("from_port")
        to_port = rule.get("to_port")
        if from_port is None or to_port is None:
            continue
        try:
            port_range = range(int(from_port), int(to_port) + 1)
        except (TypeError, ValueError):
            continue
        exposed = sorted(port for port in _SENSITIVE_INGRESS_PORTS if port in port_range)
        for port in exposed:
            findings.append(
                Finding(
                    rule_id="sg.open_ingress.v1",
                    severity="critical" if port in {22, 3389} else "high",
                    confidence=0.97,
                    evidence={
                        "port": port,
                        "service": _SENSITIVE_INGRESS_PORTS[port],
                        "protocol": rule.get("protocol"),
                        "cidr": cidr,
                    },
                )
            )
    return findings
