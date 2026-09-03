"""
Analyzer Agent (spec section 4.2) — orchestrates the deterministic rule
engine (services.analyzer.rules, carried over from the original blueprint
and real/testable today) and the sklearn IsolationForest ML layer
(services.analyzer.isolation_forest) over one Monitor Agent run's
multi-cloud fleet.

A resource already flagged by a deterministic rule is not re-flagged by the
ML layer — IsolationForest exists to catch what the hand-tuned thresholds
miss, not to duplicate them.
"""

from __future__ import annotations

import logging

from packages.schemas.unified_resource import UnifiedResource
from services.analyzer import isolation_forest, rules
from services.analyzer.models import EBSVolume, MetricSample

logger = logging.getLogger(__name__)


def _metric_samples(resource: UnifiedResource) -> list[MetricSample]:
    cpu_samples = resource.metrics_cpu_samples
    network_samples = resource.metrics_network_bytes_samples
    return [
        MetricSample(
            cpu=cpu_samples[i],
            network_bytes=network_samples[i] if i < len(network_samples) else 0.0,
            hour=12,  # daily samples carry no hour-of-day signal yet — see rules.py note
        )
        for i in range(len(cpu_samples))
    ]


def analyze(resources: list[UnifiedResource], daily_costs: list[float]) -> list[dict]:
    findings: list[dict] = []

    for resource in resources:
        samples = _metric_samples(resource)
        tags = resource.tags

        for finding in (
            rules.classify_idle(samples, tags),
            rules.classify_over_provisioned(samples, tags),
            rules.classify_nonprod_schedule(samples, tags, resource.environment),
        ):
            if finding:
                findings.append(finding.to_dict(resource.id))

        if resource.resource_type == "ebs_volume" and resource.state == "available":
            # Approximation: UnifiedResource doesn't carry a state-transition
            # timestamp, so an "available" volume is assumed to have been
            # unattached long enough to clear classify_unattached_ebs's
            # 24h minimum window.
            volume = EBSVolume(volume_id=resource.id, state=resource.state, unattached_hours=48.0)
            finding = rules.classify_unattached_ebs(volume, tags)
            if finding:
                findings.append(finding.to_dict(resource.id))

    spend_finding = rules.classify_spend_anomaly(daily_costs)
    if spend_finding:
        findings.append(spend_finding.to_dict("account-level"))

    already_flagged = {f["resource_id"] for f in findings}
    ml_findings = [f for f in isolation_forest.detect_anomalies(resources) if f["resource_id"] not in already_flagged]
    findings.extend(ml_findings)

    logger.info(
        "analyzer.service: %d finding(s) (%d rule-based, %d ML) from %d resource(s)",
        len(findings),
        len(findings) - len(ml_findings),
        len(ml_findings),
        len(resources),
    )
    return findings
