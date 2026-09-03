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

    def to_dict(self, resource_id: str) -> dict[str, Any]:
        return {
            "resource_id": resource_id,
            "rule_id": self.rule_id,
            "severity": self.severity,
            "confidence": self.confidence,
            "evidence": self.evidence,
        }
