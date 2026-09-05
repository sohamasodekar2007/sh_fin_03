from __future__ import annotations

import pytest

from forecast_anomaly.baseline_forecast import forecast_next_day
from forecast_anomaly.detector import compare_to_forecast
from forecast_anomaly.guard import ForecastAnomalyGuard
from forecast_anomaly.schemas import DailyCostPoint


def test_forecast_next_day_requires_history():
    with pytest.raises(ValueError):
        forecast_next_day([])


def test_forecast_next_day_flat_series():
    history = [100.0] * 10
    assert forecast_next_day(history) == pytest.approx(100.0)


def test_forecast_next_day_uses_seasonal_blend_with_enough_history():
    # 7 days ago was 200, trailing week is otherwise 100 — blend should
    # sit between the two, not equal either one exactly.
    history = [200.0, 100.0, 100.0, 100.0, 100.0, 100.0, 100.0]
    forecast = forecast_next_day(history)
    assert 100.0 < forecast < 200.0


def test_compare_to_forecast_normal_when_within_watch_threshold():
    result = compare_to_forecast("2026-09-01", predicted_cost=100.0, actual_cost=105.0)
    assert result.severity == "normal"
    assert result.is_anomaly is False


def test_compare_to_forecast_never_flags_underage_as_anomaly():
    result = compare_to_forecast("2026-09-01", predicted_cost=100.0, actual_cost=40.0)
    assert result.overage_pct < 0
    assert result.severity == "normal"
    assert result.is_anomaly is False


def test_compare_to_forecast_escalates_through_severity_tiers():
    watch = compare_to_forecast("d", predicted_cost=100.0, actual_cost=115.0)
    warning = compare_to_forecast("d", predicted_cost=100.0, actual_cost=130.0)
    critical = compare_to_forecast("d", predicted_cost=100.0, actual_cost=160.0)
    assert watch.severity == "watch"
    assert warning.severity == "warning"
    assert critical.severity == "critical"
    assert all(r.is_anomaly for r in (watch, warning, critical))


def test_compare_to_forecast_caps_overage_for_zero_predicted():
    result = compare_to_forecast("d", predicted_cost=0.0, actual_cost=500.0)
    assert result.overage_pct == 1_000_000.0
    assert result.severity == "critical"


def test_compare_to_forecast_zero_predicted_zero_actual_is_normal():
    result = compare_to_forecast("d", predicted_cost=0.0, actual_cost=0.0)
    assert result.overage_pct == 0.0
    assert result.severity == "normal"


def test_guard_returns_empty_for_insufficient_history():
    guard = ForecastAnomalyGuard()
    assert guard.evaluate([DailyCostPoint(date="2026-09-01", actual_cost=100.0)]) == []
    assert guard.evaluate([]) == []


def test_guard_walk_forward_never_sees_its_own_actual():
    # A spike planted only on the final day must not leak into that same
    # day's own forecast — if it did, the model would "predict" the
    # spike and overage_pct would come out near zero instead of large.
    dates = [f"2026-08-{d:02d}" for d in range(1, 15)]
    costs = [100.0] * 13 + [500.0]
    history = [DailyCostPoint(date=d, actual_cost=c) for d, c in zip(dates, costs)]

    guard = ForecastAnomalyGuard(evaluate_last_n_days=3)
    results = guard.evaluate(history)

    assert len(results) == 3
    last = results[-1]
    assert last.date == dates[-1]
    assert last.actual_cost == 500.0
    assert last.severity == "critical"
    assert last.overage_pct > 100


def test_guard_flat_history_produces_no_anomalies():
    dates = [f"2026-08-{d:02d}" for d in range(1, 11)]
    history = [DailyCostPoint(date=d, actual_cost=100.0) for d in dates]
    guard = ForecastAnomalyGuard(evaluate_last_n_days=5)
    results = guard.evaluate(history)
    assert len(results) == 5
    assert all(not r.is_anomaly for r in results)
