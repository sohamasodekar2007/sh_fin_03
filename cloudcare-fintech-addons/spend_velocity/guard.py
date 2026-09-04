"""SpendVelocityGuard — the orchestrator that ties detector + policy +
notify together. This is the "circuit breaker" object a caller (the
demo script, the standalone API, or eventually
sh_fin_03/services/executor) holds onto and calls `.evaluate()` on."""

from __future__ import annotations

from datetime import datetime

from .detector import classify_severity, compute_velocity, cusum_drift, reference_stats
from .notify import LoggingNotificationSink, NotificationSink
from .schemas import SpendSample, VelocityAlert


class SpendVelocityGuard:
    def __init__(
        self,
        *,
        current_window_hours: float = 2.0,
        baseline_window_hours: float = 168.0,
        min_baseline_samples: int = 8,
        notification_sink: NotificationSink | None = None,
    ) -> None:
        self._current_window_hours = current_window_hours
        self._baseline_window_hours = baseline_window_hours
        self._min_baseline_samples = min_baseline_samples
        self._sink = notification_sink or LoggingNotificationSink()

    def evaluate(
        self,
        samples: list[SpendSample],
        *,
        is_production: bool,
        now: datetime | None = None,
        baseline_period_rates: list[float] | None = None,
        current_period_rates: list[float] | None = None,
    ) -> VelocityAlert | None:
        """Returns None when there's nothing worth surfacing (no data in
        the current window, or severity resolves to "low"). Otherwise
        sends the alert through the notification sink and returns it."""
        reading = compute_velocity(
            samples,
            now=now,
            current_window_hours=self._current_window_hours,
            baseline_window_hours=self._baseline_window_hours,
            min_baseline_samples=self._min_baseline_samples,
        )
        if reading is None:
            return None

        severity = classify_severity(reading)
        if severity == "low":
            return None

        tags = samples[-1].tags if samples else {}
        from .policy import decide_containment  # local import avoids a cycle at module load time

        action, requires_human_approval = decide_containment(severity, is_production=is_production, tags=tags)

        drift_confirmed = None
        if baseline_period_rates and current_period_rates:
            ref_mean, ref_stddev = reference_stats(baseline_period_rates)
            drift_confirmed = cusum_drift(current_period_rates, reference_mean=ref_mean, reference_stddev=ref_stddev)

        rationale = self._build_rationale(reading, severity, action, drift_confirmed)
        alert = VelocityAlert(
            scope=reading.scope,
            severity=severity,
            reading=reading,
            recommended_action=action,
            rationale=rationale,
            requires_human_approval=requires_human_approval,
            projected_24h_cost=round(reading.current_hourly_rate * 24, 2),
        )
        self._sink.send(alert)
        return alert

    @staticmethod
    def _build_rationale(reading, severity, action, drift_confirmed: bool | None) -> str:
        if reading.baseline_hourly_rate <= 1e-9:
            ratio_txt = "new spend with no prior baseline"
        else:
            ratio_txt = f"{reading.velocity_ratio:.1f}x baseline"

        parts = [
            f"Estimated hourly spend for '{reading.scope}' is {ratio_txt} "
            f"(₹{reading.current_hourly_rate:,.2f}/hr now vs ₹{reading.baseline_hourly_rate:,.2f}/hr baseline, "
            f"{reading.baseline_sample_count} baseline samples).",
            "This is a usage-metric-derived estimate, not a billed figure — Cost Explorer/Budgets data lags "
            "8-24h, which is exactly the gap this check exists to close.",
        ]
        if reading.confidence < 0.5:
            parts.append("Confidence is low — baseline history is thin; treat this as an early signal, not a certainty.")
        if drift_confirmed is True:
            parts.append("Confirmed as a sustained drift (CUSUM), not a single noisy sample.")
        elif drift_confirmed is False:
            parts.append("CUSUM drift check did not confirm a sustained trend — could still be a single spike.")
        parts.append(f"Recommended response: {action.replace('_', ' ')}.")
        return " ".join(parts)
