from __future__ import annotations

from .baseline_forecast import forecast_next_day
from .detector import compare_to_forecast
from .schemas import DailyCostPoint, ForecastComparison


class ForecastAnomalyGuard:
    """Walk-forward evaluator: for each of the last `evaluate_last_n_days`
    days, forecasts that day using only the days strictly before it, then
    compares the forecast to what actually happened. This is real
    walk-forward validation (each day's forecast never sees its own
    actual), not a lookahead-biased fit."""

    def __init__(
        self,
        *,
        watch_pct: float = 10.0,
        warning_pct: float = 25.0,
        critical_pct: float = 50.0,
        evaluate_last_n_days: int = 7,
    ) -> None:
        self._watch_pct = watch_pct
        self._warning_pct = warning_pct
        self._critical_pct = critical_pct
        self._evaluate_last_n_days = evaluate_last_n_days

    def evaluate(self, history: list[DailyCostPoint]) -> list[ForecastComparison]:
        """`history` must be chronologically ordered. Returns one
        ForecastComparison per evaluated day, oldest first. Returns an
        empty list (never raises) when there's under 2 days of history —
        that's "nothing to evaluate yet," not an error condition."""
        if len(history) < 2:
            return []

        costs = [p.actual_cost for p in history]
        start = max(1, len(costs) - self._evaluate_last_n_days)

        results: list[ForecastComparison] = []
        for i in range(start, len(costs)):
            predicted = forecast_next_day(costs[:i])
            results.append(
                compare_to_forecast(
                    history[i].date,
                    predicted,
                    costs[i],
                    watch_pct=self._watch_pct,
                    warning_pct=self._warning_pct,
                    critical_pct=self._critical_pct,
                )
            )
        return results
