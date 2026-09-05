from __future__ import annotations

from .schemas import ForecastComparison, ForecastSeverity

_OVERAGE_CAP = 1_000_000.0


def _classify(overage_pct: float, *, watch_pct: float, warning_pct: float, critical_pct: float) -> tuple[ForecastSeverity, bool]:
    """Only positive overage escalates severity — coming in *under*
    forecast is never an anomaly here, deliberately, even though
    overage_pct is negative in that case and would otherwise satisfy a
    naive abs()-based threshold."""
    if overage_pct < watch_pct:
        return "normal", False
    if overage_pct < warning_pct:
        return "watch", True
    if overage_pct < critical_pct:
        return "warning", True
    return "critical", True


def compare_to_forecast(
    date: str,
    predicted_cost: float,
    actual_cost: float,
    *,
    watch_pct: float = 10.0,
    warning_pct: float = 25.0,
    critical_pct: float = 50.0,
) -> ForecastComparison:
    """A predicted_cost of ~0 with real actual spend is capped at a large
    sentinel overage rather than a divide-by-zero — same discipline as
    spend_velocity.detector's ratio cap, and for the same reason: this
    must always stay a normal JSON float."""
    if predicted_cost <= 1e-9:
        overage_pct = _OVERAGE_CAP if actual_cost > 1e-9 else 0.0
    else:
        overage_pct = round((actual_cost - predicted_cost) / predicted_cost * 100, 2)

    severity, is_anomaly = _classify(
        overage_pct, watch_pct=watch_pct, warning_pct=warning_pct, critical_pct=critical_pct
    )

    if severity == "normal":
        rationale = (
            f"{date}: actual ₹{actual_cost:,.2f} vs. predicted ₹{predicted_cost:,.2f} "
            f"({overage_pct:+.1f}%) — within normal forecast variance."
        )
    else:
        rationale = (
            f"{date}: actual cost ₹{actual_cost:,.2f} landed {overage_pct:.1f}% above the ₹{predicted_cost:,.2f} "
            f"forecast for this day. Predicted value is a walk-forward estimate — see baseline_forecast.py's "
            f"docstring for the model used (or services.forecasting.select.select_forecast once merged)."
        )

    return ForecastComparison(
        date=date,
        predicted_cost=round(predicted_cost, 4),
        actual_cost=round(actual_cost, 4),
        overage_pct=overage_pct,
        severity=severity,
        is_anomaly=is_anomaly,
        rationale=rationale,
    )
