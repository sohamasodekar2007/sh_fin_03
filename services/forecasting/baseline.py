"""
Baseline forecasting methods — blueprint §5.2.

Both functions accept a list of observed daily cost values (floats, ordered
oldest-first) and return a list of predicted values for the next `horizon`
days.  They are fast, dependency-free, and always produce a result regardless
of series length, making them the guaranteed fallback tier.
"""

from __future__ import annotations


def moving_average(series: list[float], horizon: int = 30, window: int = 7) -> list[float]:
    """
    Predict the next `horizon` values using the rolling mean of the last
    `window` observations.

    If the series is shorter than `window`, the whole series is used.
    Always returns exactly `horizon` values.

    Args:
        series:  Historical daily cost observations, oldest-first.
        horizon: Number of future days to predict.
        window:  Look-back window size for the rolling mean.

    Returns:
        List of `horizon` predicted float values.
    """
    if not series:
        return [0.0] * horizon

    effective_window = min(window, len(series))
    mean = sum(series[-effective_window:]) / effective_window
    return [round(mean, 4) for _ in range(horizon)]


def seasonal_naive(series: list[float], horizon: int = 30, period: int = 7) -> list[float]:
    """
    Predict the next `horizon` values by repeating the last observed
    seasonal cycle (default: weekly, period=7).

    If the series is shorter than `period`, falls back to moving_average.

    Args:
        series:  Historical daily cost observations, oldest-first.
        horizon: Number of future days to predict.
        period:  Seasonal period length in days.

    Returns:
        List of `horizon` predicted float values.
    """
    if len(series) < period:
        # Not enough history for a full cycle — fall back to moving average.
        return moving_average(series, horizon=horizon)

    last_cycle = series[-period:]
    predictions: list[float] = []
    for i in range(horizon):
        predictions.append(round(last_cycle[i % period], 4))
    return predictions
