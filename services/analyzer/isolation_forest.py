"""
Analyzer Agent — ML clustering layer (spec section 4.2).

sklearn's IsolationForest over a feature matrix built from every resource
in the current run: [cpu_p95, memory_p95, network_p95, effective_cost,
list_cost - effective_cost]. Flags resources the *deterministic* rules in
rules.py miss — non-obvious cost spikes, orphaned disks, and
over-provisioned nodes that don't cross any single hand-tuned threshold but
sit apart from the rest of the fleet in the joint feature space.

Unsupervised — no labels required, retrained fresh every Analyzer run
against that run's own fleet (a resource is "anomalous" relative to its
peers this run, not against a fixed historical baseline).
"""

from __future__ import annotations

from typing import Any

from packages.schemas.unified_resource import UnifiedResource
from services.analyzer.models import Finding

MIN_RESOURCES_FOR_FOREST = 8  # a forest fit on a handful of points is noise, not signal


def _feature_vector(resource: UnifiedResource) -> list[float]:
    return [
        resource.metrics_cpu_utilization_p95 or 0.0,
        resource.metrics_memory_utilization_p95 or 50.0,
        (resource.metrics_network_bytes_p95 or 0.0) / 1_000_000,  # scale to MB
        resource.effective_cost,
        max(0.0, resource.list_cost - resource.effective_cost),
    ]


def detect_anomalies(resources: list[UnifiedResource], contamination: float = 0.1) -> list[dict[str, Any]]:
    """Returns Finding.to_dict()-shaped dicts for resources IsolationForest
    scores as outliers (label == -1). Degrades to [] below
    MIN_RESOURCES_FOR_FOREST rather than fitting a meaningless forest — the
    deterministic rules already cover small fleets."""
    if len(resources) < MIN_RESOURCES_FOR_FOREST:
        return []

    from sklearn.ensemble import IsolationForest

    matrix = [_feature_vector(r) for r in resources]
    model = IsolationForest(contamination=contamination, random_state=42, n_estimators=200)
    labels = model.fit_predict(matrix)  # -1 == anomaly, 1 == inlier
    scores = model.decision_function(matrix)  # lower == more anomalous

    findings: list[dict[str, Any]] = []
    for resource, label, score, features in zip(resources, labels, scores, matrix):
        if label != -1:
            continue
        findings.append(
            Finding(
                rule_id="ml.isolation_forest.v1",
                severity="medium",
                confidence=round(min(0.99, max(0.5, 0.5 - float(score))), 3),
                evidence={
                    "anomaly_score": round(float(score), 4),
                    "cpu_p95": features[0],
                    "memory_p95": features[1],
                    "network_p95_mb": features[2],
                    "effective_cost_usd": features[3],
                    "unrealized_discount_usd": features[4],
                    "contamination": contamination,
                    "fleet_size": len(resources),
                },
            ).to_dict(resource.id)
        )
    return findings
