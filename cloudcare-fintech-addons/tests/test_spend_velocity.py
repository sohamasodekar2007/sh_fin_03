from __future__ import annotations

from datetime import datetime, timedelta, timezone

from spend_velocity.detector import classify_severity, compute_velocity, cusum_drift, reference_stats
from spend_velocity.guard import SpendVelocityGuard
from spend_velocity.notify import NullNotificationSink
from spend_velocity.policy import decide_containment
from spend_velocity.schemas import SpendSample

NOW = datetime(2026, 9, 5, 12, 0, tzinfo=timezone.utc)


def _flat_samples(scope="svc-a", hourly_rate=100.0, hours=48, interval_minutes=30, tags=None):
    samples = []
    t = NOW - timedelta(hours=hours)
    per_sample = hourly_rate * (interval_minutes / 60.0)
    while t < NOW:
        samples.append(SpendSample(scope=scope, timestamp=t, estimated_cost=per_sample, tags=tags or {}))
        t += timedelta(minutes=interval_minutes)
    return samples


def _spiked_samples(scope="svc-a", baseline_rate=100.0, spike_rate=1500.0, spike_hours=2, tags=None):
    samples = _flat_samples(scope=scope, hourly_rate=baseline_rate, hours=168, tags=tags)
    t = NOW - timedelta(hours=spike_hours)
    per_sample = spike_rate * 0.5  # 30-minute buckets
    while t < NOW:
        samples.append(SpendSample(scope=scope, timestamp=t, estimated_cost=per_sample, tags=tags or {}))
        t += timedelta(minutes=30)
    return samples


def test_compute_velocity_returns_none_with_no_samples():
    assert compute_velocity([], now=NOW) is None


def test_compute_velocity_returns_none_when_current_window_empty():
    # All samples are older than the current window.
    samples = [SpendSample(scope="svc-a", timestamp=NOW - timedelta(hours=10), estimated_cost=5.0)]
    assert compute_velocity(samples, now=NOW, current_window_hours=1.0) is None


def test_compute_velocity_flat_spend_has_ratio_near_one():
    samples = _flat_samples(hourly_rate=100.0)
    reading = compute_velocity(samples, now=NOW)
    assert reading is not None
    assert 0.9 <= reading.velocity_ratio <= 1.1
    assert classify_severity(reading) == "low"


def test_compute_velocity_detects_large_spike():
    samples = _spiked_samples(baseline_rate=100.0, spike_rate=1200.0)
    reading = compute_velocity(samples, now=NOW)
    assert reading is not None
    assert reading.velocity_ratio >= 10
    assert classify_severity(reading) == "critical"


def test_compute_velocity_caps_ratio_for_zero_baseline():
    t = NOW - timedelta(minutes=30)
    samples = [SpendSample(scope="svc-new", timestamp=t, estimated_cost=500.0)]
    reading = compute_velocity(samples, now=NOW, min_baseline_samples=1)
    assert reading is not None
    assert reading.velocity_ratio == 1_000_000.0
    # A true zero-to-nonzero jump is critical regardless of confidence —
    # it isn't an averaging claim thin history could get wrong.
    assert classify_severity(reading) == "critical"


def test_classify_severity_downgrades_low_confidence_readings():
    # Thin baseline (below min_baseline_samples) caps confidence low,
    # which must prevent "critical" even with a huge nominal ratio.
    samples = _spiked_samples(baseline_rate=100.0, spike_rate=5000.0)
    reading = compute_velocity(samples, now=NOW, min_baseline_samples=10_000)
    assert reading.confidence < 0.3
    assert classify_severity(reading) != "critical"


# Realistic day-to-day noise (mean 100, stddev ~13.7) — tight enough that
# a genuine trend is detectable, loose enough that a single moderate
# outlier shouldn't already be a 5-sigma event on its own.
_STABLE_BASELINE = [80.0, 120.0, 90.0, 110.0, 85.0, 115.0, 95.0, 105.0]


def test_cusum_drift_requires_minimum_history():
    mean, stddev = reference_stats(_STABLE_BASELINE)
    assert cusum_drift([10.0, 20.0, 30.0], reference_mean=mean, reference_stddev=stddev) is False


def test_cusum_drift_confirms_sustained_rise():
    mean, stddev = reference_stats(_STABLE_BASELINE)
    # Consistently ~50 above the mean for several periods in a row — a
    # real drift, not one lucky/unlucky sample.
    current = [150.0, 155.0, 160.0, 165.0]
    assert cusum_drift(current, reference_mean=mean, reference_stddev=stddev) is True


def test_cusum_drift_rejects_single_noisy_spike():
    mean, stddev = reference_stats(_STABLE_BASELINE)
    # One elevated-but-plausible point surrounded by normal ones — the
    # cumulative statistic should decay back down before crossing
    # threshold, unlike the sustained-rise case above.
    current = [100.0, 150.0, 101.0, 99.0]
    assert cusum_drift(current, reference_mean=mean, reference_stddev=stddev) is False


def test_cusum_drift_rejects_when_reference_is_degenerate():
    # A zero-variance reference (e.g. only one baseline sample) must not
    # be treated as "any deviation is infinite sigma" — reference_stddev
    # of ~0 disables the check rather than firing on everything.
    assert cusum_drift([50.0, 60.0, 70.0, 80.0], reference_mean=10.0, reference_stddev=0.0) is False


def test_decide_containment_never_auto_throttles_production():
    action, requires_approval = decide_containment("high", is_production=True, tags={})
    assert action == "escalate_supervisor"
    assert requires_approval is True


def test_decide_containment_allows_throttle_for_non_prod():
    action, requires_approval = decide_containment("high", is_production=False, tags={})
    assert action == "throttle_non_prod"
    assert requires_approval is False


def test_decide_containment_respects_exclude_tag():
    action, requires_approval = decide_containment(
        "critical", is_production=False, tags={"cloudcare:exclude": "true"}
    )
    assert action == "monitor_only"
    assert requires_approval is True


def test_decide_containment_respects_max_risk_ceiling():
    action, requires_approval = decide_containment(
        "critical", is_production=False, tags={"cloudcare:max-risk": "low"}
    )
    assert requires_approval is True
    assert action == "escalate_supervisor"


def test_guard_evaluate_returns_none_for_flat_spend():
    guard = SpendVelocityGuard(notification_sink=NullNotificationSink())
    alert = guard.evaluate(_flat_samples(), is_production=False, now=NOW)
    assert alert is None


def test_guard_evaluate_returns_alert_for_spike_and_sends_it():
    sent = []

    class RecordingSink:
        def send(self, alert):
            sent.append(alert)

    guard = SpendVelocityGuard(notification_sink=RecordingSink())
    samples = _spiked_samples(tags={"cloudcare:environment": "production"})
    baseline_rates = [100.0, 98.0, 101.0, 99.0, 102.0, 100.0]
    current_rates = [1500.0, 1480.0, 1510.0, 1495.0]
    alert = guard.evaluate(
        samples,
        is_production=True,
        now=NOW,
        baseline_period_rates=baseline_rates,
        current_period_rates=current_rates,
    )

    assert alert is not None
    assert alert.severity == "critical"
    assert alert.requires_human_approval is True
    assert "8-24h" in alert.rationale  # honesty disclaimer must always be present
    assert "sustained drift" in alert.rationale  # CUSUM confirmation should be reflected in the rationale
    assert sent == [alert]
