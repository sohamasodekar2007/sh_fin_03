"""Pure detection math — no I/O, no AWS calls, fully unit-testable.

Two signals, deliberately kept separate:

1. `compute_velocity` — a windowed rate-ratio (current hourly estimate vs
   a trailing baseline). Cheap, always available, but a single noisy
   sample can trigger it.
2. `cusum_drift` — a one-sided CUSUM change-point check over a sequence
   of period rates, confirming the rise is a *sustained* drift rather
   than one spike. `guard.py` uses this as a secondary confirmation
   signal, not a replacement for (1).
"""

from __future__ import annotations

from datetime import datetime, timedelta

from .schemas import Severity, SpendSample, VelocityReading

_RATIO_CAP = 1_000_000.0


def _hourly_rate(samples: list[SpendSample], window_start: datetime, window_end: datetime) -> tuple[float, int]:
    """Rate is cost-per-actually-observed-hour, not cost divided by the
    nominal window length. When history doesn't reach all the way back
    to window_start (a cold-start scope, or a baseline window wider than
    the account's age), dividing by the full nominal window would dilute
    the rate and understate it — coverage is clamped to where real data
    starts instead."""
    in_window = [s for s in samples if window_start <= s.timestamp < window_end]
    if not in_window:
        return 0.0, 0
    coverage_start = max(window_start, min(s.timestamp for s in in_window))
    hours = max((window_end - coverage_start).total_seconds() / 3600.0, 1e-9)
    return sum(s.estimated_cost for s in in_window) / hours, len(in_window)


def compute_velocity(
    samples: list[SpendSample],
    *,
    now: datetime | None = None,
    current_window_hours: float = 2.0,
    baseline_window_hours: float = 168.0,
    min_baseline_samples: int = 8,
) -> VelocityReading | None:
    """None means "nothing to say" — either no samples at all, or nothing
    fell inside the current window. Never fabricates a reading for a
    window with zero observations in it."""
    if not samples:
        return None
    scope = samples[0].scope
    now = now or max(s.timestamp for s in samples)
    current_start = now - timedelta(hours=current_window_hours)
    baseline_end = current_start
    baseline_start = baseline_end - timedelta(hours=baseline_window_hours)

    current_rate, current_n = _hourly_rate(samples, current_start, now)
    if current_n == 0:
        return None
    baseline_rate, baseline_n = _hourly_rate(samples, baseline_start, baseline_end)

    if baseline_n < min_baseline_samples:
        # Not "no confidence" — just capped low, since a fresh scope with
        # a real spike still deserves a (low-confidence) alert, not silence.
        confidence = round(0.15 + 0.15 * min(baseline_n / max(min_baseline_samples, 1), 1.0), 3)
    else:
        confidence = round(min(1.0, baseline_n / (min_baseline_samples * 4)), 3)

    if baseline_rate <= 1e-9:
        ratio = _RATIO_CAP if current_rate > 0 else 1.0
    else:
        ratio = min(current_rate / baseline_rate, _RATIO_CAP)

    return VelocityReading(
        scope=scope,
        window_end=now,
        baseline_hourly_rate=round(baseline_rate, 4),
        current_hourly_rate=round(current_rate, 4),
        velocity_ratio=round(ratio, 4),
        sample_count=current_n,
        baseline_sample_count=baseline_n,
        confidence=confidence,
    )


def classify_severity(reading: VelocityReading) -> Severity:
    """Confidence gates severity downward — a reading built on thin
    history is never allowed to read as "critical," no matter how large
    the ratio looks, because a handful of samples can produce an
    arbitrarily large ratio by chance."""
    if reading.baseline_hourly_rate <= 1e-9 and reading.current_hourly_rate > 0:
        # A true zero-to-nonzero jump isn't an averaging claim that thin
        # history could get wrong — it's the factual observation "there
        # was no cost here, now there is." That doesn't need baseline
        # confidence to be trustworthy, so it bypasses the gate below.
        return "critical"
    if reading.confidence < 0.3:
        return "low" if reading.velocity_ratio < 20 else "medium"
    if reading.velocity_ratio >= 10:
        return "critical"
    if reading.velocity_ratio >= 5:
        return "high"
    if reading.velocity_ratio >= 2:
        return "medium"
    return "low"


def reference_stats(baseline_period_rates: list[float]) -> tuple[float, float]:
    """Mean and stddev of a *stable* reference period, meant to be
    computed from the baseline window only. Deliberately a separate call
    from cusum_drift — computing the reference from a series that already
    contains the shift you're trying to detect biases the mean upward and
    silently weakens detection, which is what an earlier version of this
    function got wrong."""
    if not baseline_period_rates:
        return 0.0, 0.0
    mean = sum(baseline_period_rates) / len(baseline_period_rates)
    variance = sum((r - mean) ** 2 for r in baseline_period_rates) / len(baseline_period_rates)
    return mean, variance**0.5


def cusum_drift(
    current_period_rates: list[float],
    *,
    reference_mean: float,
    reference_stddev: float,
    k_stddev: float = 0.5,
    threshold_stddev: float = 5.0,
) -> bool:
    """One-sided CUSUM: True only when the cumulative deviation of
    `current_period_rates` above (reference_mean + k*stddev) crosses
    threshold_stddev*stddev — a sustained rise relative to a *known
    stable* reference, not one outlier period. `reference_mean` /
    `reference_stddev` must come from `reference_stats()` on the baseline
    window, not from current_period_rates itself. Returns False (not
    True) when there isn't enough history or the reference is degenerate
    (stddev == 0), since "unconfirmed" must never look like "confirmed
    absence of drift" to a caller."""
    if len(current_period_rates) < 4 or reference_stddev <= 1e-9:
        return False
    k = k_stddev * reference_stddev
    threshold = threshold_stddev * reference_stddev
    cumulative = 0.0
    for rate in current_period_rates:
        cumulative = max(0.0, cumulative + (rate - reference_mean - k))
        if cumulative > threshold:
            return True
    return False
