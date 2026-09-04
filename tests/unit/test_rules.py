"""
Unit tests for all five analyzer rules.
No AWS dependency — only synthetic MetricSample / EBSVolume / cost-series data.
"""

import pytest

from services.analyzer.rules import (
    EBSVolume,
    Finding,
    MetricSample,
    classify_idle,
    classify_nonprod_schedule,
    classify_over_provisioned,
    classify_spend_anomaly,
    classify_unattached_ebs,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _idle_metrics(n: int = 7) -> list[MetricSample]:
    """n samples with CPU < 5 % and network < 10 MB — triggers idle rule."""
    return [MetricSample(cpu=2.0, network_bytes=1_000_000) for _ in range(n)]


def _busy_metrics(n: int = 7) -> list[MetricSample]:
    """n samples clearly above idle/over-provisioned thresholds."""
    return [MetricSample(cpu=60.0, network_bytes=50_000_000) for _ in range(n)]


def _off_hour_idle(n: int = 14) -> list[MetricSample]:
    """14 samples: business-hour CPU normal, off-hour CPU near zero."""
    samples = []
    for i in range(n):
        samples.append(MetricSample(cpu=0.5, network_bytes=500_000, hour=2))   # 02:00 off-hours
    return samples


def _flat_costs(value: float, length: int = 15) -> list[float]:
    """Flat daily cost series — no anomaly expected."""
    return [value] * length


def _spiked_costs(baseline: float = 100.0) -> list[float]:
    """14 stable days + 1 spike day well above 2 std-devs."""
    costs = [baseline] * 14
    costs.append(baseline * 5)   # huge spike
    return costs


# ---------------------------------------------------------------------------
# Rule 1 — classify_idle
# ---------------------------------------------------------------------------

class TestClassifyIdle:
    def test_triggers_when_cpu_and_network_low(self):
        result = classify_idle(_idle_metrics(), tags={})
        assert isinstance(result, Finding)
        assert result.rule_id == "ec2.idle.v1"
        assert result.severity == "medium"

    def test_does_not_trigger_when_cpu_high(self):
        result = classify_idle(_busy_metrics(), tags={})
        assert result is None

    def test_does_not_trigger_with_exclude_tag(self):
        result = classify_idle(_idle_metrics(), tags={"cloudcare:exclude": "true"})
        assert result is None

    def test_does_not_trigger_with_insufficient_samples(self):
        result = classify_idle(_idle_metrics(n=5), tags={})
        assert result is None

    def test_does_not_trigger_when_network_high(self):
        metrics = [MetricSample(cpu=2.0, network_bytes=20_000_000) for _ in range(7)]
        result = classify_idle(metrics, tags={})
        assert result is None


# ---------------------------------------------------------------------------
# Rule 2 — classify_over_provisioned
# ---------------------------------------------------------------------------

class TestClassifyOverProvisioned:
    def test_triggers_when_cpu_p95_below_25(self):
        metrics = [MetricSample(cpu=10.0, network_bytes=0, memory_used_pct=30.0) for _ in range(14)]
        result = classify_over_provisioned(metrics, tags={})
        assert isinstance(result, Finding)
        assert result.rule_id == "ec2.overprovisioned.v1"
        assert result.severity == "low"

    def test_does_not_trigger_when_cpu_high(self):
        metrics = [MetricSample(cpu=80.0, network_bytes=0) for _ in range(14)]
        result = classify_over_provisioned(metrics, tags={})
        assert result is None

    def test_does_not_trigger_with_exclude_tag(self):
        metrics = [MetricSample(cpu=5.0, network_bytes=0) for _ in range(14)]
        result = classify_over_provisioned(metrics, tags={"cloudcare:exclude": "true"})
        assert result is None

    def test_does_not_trigger_with_insufficient_samples(self):
        metrics = [MetricSample(cpu=5.0, network_bytes=0) for _ in range(13)]
        result = classify_over_provisioned(metrics, tags={})
        assert result is None


# ---------------------------------------------------------------------------
# Rule 3 — classify_unattached_ebs
# ---------------------------------------------------------------------------

class TestClassifyUnattachedEBS:
    def test_triggers_for_available_volume(self):
        vol = EBSVolume(volume_id="vol-abc123", state="available")
        result = classify_unattached_ebs(vol, tags={})
        assert isinstance(result, Finding)
        assert result.rule_id == "ebs.unattached.v1"
        assert result.evidence["volume_id"] == "vol-abc123"
        assert result.evidence["window_hours"] == 24

    def test_does_not_trigger_for_attached_volume(self):
        vol = EBSVolume(volume_id="vol-xyz", state="in-use")
        result = classify_unattached_ebs(vol, tags={})
        assert result is None

    def test_does_not_trigger_with_exclude_tag(self):
        vol = EBSVolume(volume_id="vol-abc123", state="available")
        result = classify_unattached_ebs(vol, tags={"cloudcare:exclude": "true"})
        assert result is None


# ---------------------------------------------------------------------------
# Rule 4 — classify_nonprod_schedule
# ---------------------------------------------------------------------------

class TestClassifyNonprodSchedule:
    def test_triggers_for_off_hours_idle_dev(self):
        result = classify_nonprod_schedule(_off_hour_idle(), tags={}, environment="dev")
        assert isinstance(result, Finding)
        assert result.rule_id == "ec2.nonprod_schedule.v1"
        assert result.evidence["environment"] == "dev"

    def test_does_not_trigger_for_prod(self):
        result = classify_nonprod_schedule(_off_hour_idle(), tags={}, environment="prod")
        assert result is None

    def test_does_not_trigger_with_exclude_tag(self):
        result = classify_nonprod_schedule(
            _off_hour_idle(), tags={"cloudcare:exclude": "true"}, environment="staging"
        )
        assert result is None

    def test_does_not_trigger_with_insufficient_samples(self):
        result = classify_nonprod_schedule(_off_hour_idle(n=10), tags={}, environment="dev")
        assert result is None

    def test_does_not_trigger_when_off_hours_cpu_high(self):
        # off-hours CPU is high — instance runs at night too
        metrics = [MetricSample(cpu=50.0, network_bytes=0, hour=2) for _ in range(14)]
        result = classify_nonprod_schedule(metrics, tags={}, environment="dev")
        assert result is None

    def test_does_not_trigger_when_no_off_hour_samples(self):
        # all samples are during business hours
        metrics = [MetricSample(cpu=0.1, network_bytes=0, hour=10) for _ in range(14)]
        result = classify_nonprod_schedule(metrics, tags={}, environment="dev")
        assert result is None


# ---------------------------------------------------------------------------
# Rule 5 — classify_spend_anomaly
# ---------------------------------------------------------------------------

class TestClassifySpendAnomaly:
    def test_triggers_on_large_spike(self):
        result = classify_spend_anomaly(_spiked_costs(baseline=100.0))
        assert isinstance(result, Finding)
        assert result.rule_id == "cost.anomaly.v1"
        assert result.severity == "high"
        # z_score may be None when baseline std is ~0 (flat series); just verify it fired

    def test_triggers_on_spike_with_variance(self):
        # Baseline has natural variance so z_score path is exercised
        costs = [90.0, 95.0, 105.0, 100.0, 98.0, 102.0, 99.0,
                 101.0, 97.0, 103.0, 100.0, 99.0, 101.0, 100.0]
        costs.append(500.0)  # massive spike, clearly > 2 std-devs
        result = classify_spend_anomaly(costs)
        assert isinstance(result, Finding)
        assert result.rule_id == "cost.anomaly.v1"
        assert result.evidence["z_score"] > 2.0

    def test_does_not_trigger_on_flat_series(self):
        result = classify_spend_anomaly(_flat_costs(100.0))
        assert result is None

    def test_does_not_trigger_with_insufficient_data(self):
        result = classify_spend_anomaly([100.0] * 14)  # need 15+
        assert result is None

    def test_does_not_trigger_on_minor_increase(self):
        # only 1.5 std-devs above mean — below threshold
        import statistics
        base = [100.0] * 14
        std = statistics.pstdev(base[:-1]) if statistics.pstdev(base[:-1]) > 0 else 5.0
        # use a manually crafted series with real variance
        costs = [90.0, 95.0, 105.0, 100.0, 98.0, 102.0, 99.0,
                 101.0, 97.0, 103.0, 100.0, 99.0, 101.0, 100.0]
        mean = sum(costs) / len(costs)
        import math
        std = math.sqrt(sum((x - mean) ** 2 for x in costs) / len(costs))
        # spike at exactly 1.5 std — should not trigger
        mild_spike = mean + 1.5 * std
        result = classify_spend_anomaly(costs + [mild_spike])
        assert result is None

    def test_confidence_capped_at_99(self):
        # absurdly large spike — confidence must not exceed 0.99
        costs = [10.0] * 14 + [10_000.0]
        result = classify_spend_anomaly(costs)
        assert result is not None
        assert result.confidence <= 0.99
