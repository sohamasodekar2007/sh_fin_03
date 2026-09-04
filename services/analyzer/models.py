from __future__ import annotations

from dataclasses import dataclass
from typing import Any


Severity = str


@dataclass(frozen=True)
class MetricSample:
    cpu: float = 0.0
    network_bytes: float = 0.0
    memory_used_pct: float | None = None
    hour: int = 12


@dataclass(frozen=True)
class EBSVolume:
    volume_id: str
    state: str
    unattached_hours: float | None = None


@dataclass(frozen=True)
class Finding:
    rule_id: str
    severity: Severity
    confidence: float
    evidence: dict[str, Any]

    # "billable" (default): the resource has a real invoice, so acting on
    # this finding produces a real dollar saving (AWS, Azure).
    # "reclaimable_capacity": a fixed-price server (VPS) is owed its
    # monthly cost regardless of what runs on it — stopping something
    # frees capacity, not money. See services/focus/mappers/vps.py's
    # module docstring for why this distinction exists.
    savings_type: str = "billable"
    reclaimable_vcpu: float | None = None
    reclaimable_memory_mb: float | None = None

    def to_dict(self, resource_id: str) -> dict[str, Any]:
        return {
            "resource_id": resource_id,
            "rule_id": self.rule_id,
            "severity": self.severity,
            "confidence": self.confidence,
            "evidence": self.evidence,
            "savings_type": self.savings_type,
            "reclaimable_vcpu": self.reclaimable_vcpu,
            "reclaimable_memory_mb": self.reclaimable_memory_mb,
        }
