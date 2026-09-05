"""SHIM — a deliberately simple forecaster so this package runs
standalone. On merge, delete `forecast_next_day` and call
services.forecasting.select.select_forecast instead (it already picks
the lowest-MAPE model via real backtesting — Holt-Winters/Prophet-or-ARIMA
when there's 90+ days of history, seasonal-naive/moving-average
otherwise). This shim exists only to avoid pulling statsmodels/Prophet
into a standalone add-on package; it is NOT a replacement for that
module's accuracy."""

from __future__ import annotations

_SEASONAL_WINDOW = 7


def forecast_next_day(history: list[float]) -> float:
    """Blend of the trailing-7-day mean and the value exactly 7 days
    before the day being forecast (weekday seasonality) — a real, if
    simple, model, not a stub. Raises on empty history rather than
    guessing 0, since a forecast with no data behind it isn't a
    forecast."""
    if not history:
        raise ValueError("forecast_next_day requires at least 1 day of history")

    trailing = history[-_SEASONAL_WINDOW:]
    trailing_mean = sum(trailing) / len(trailing)

    if len(history) >= _SEASONAL_WINDOW:
        seasonal = history[-_SEASONAL_WINDOW]
        return round(0.6 * trailing_mean + 0.4 * seasonal, 4)
    return round(trailing_mean, 4)
