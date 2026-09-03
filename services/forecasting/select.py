"""
Model selection — blueprint §5.2 Listing 2.

select_forecast(series, horizon) builds a candidate list, backtests each
model, picks the lowest-MAPE winner, and always falls back to
moving_average when data is thin (< 14 days) or all models fail.
"""

from __future__ import annotations

import logging
from typing import Callable

from services.forecasting.backtest import backtest
from services.forecasting.baseline import moving_average, seasonal_naive
from services.forecasting.models import holt_winters, prophet_or_arima

logger = logging.getLogger(__name__)

# Minimum history required to attempt any model beyond moving_average.
_MIN_HISTORY = 14


def select_forecast(series: list[float], horizon: int = 30) -> list[float]:
    """
    Blueprint §5.2 Listing 2 — automatic model selection.

    Algorithm:
    1. If series is empty or shorter than _MIN_HISTORY, return
       moving_average immediately (guaranteed fallback, never crashes).
    2. Build a candidate list ordered from most-to-least sophisticated.
       Each candidate is a partial that fixes `horizon` so backtest() can
       call it with just the training series.
    3. Backtest every candidate; keep (mape, name, fn) tuples.
    4. Pick the candidate with the lowest MAPE.  If all MAPEs are inf
       (every model failed), fall back to moving_average.
    5. Return predictions from the winning model trained on the full series.

    Args:
        series:  Historical daily cost observations, oldest-first.
        horizon: Number of future days to predict.

    Returns:
        List of `horizon` predicted float values.
    """
    # ------------------------------------------------------------------ #
    # 1. Thin-data fast path                                               #
    # ------------------------------------------------------------------ #
    if not series:
        logger.info("select_forecast: empty series — returning zeros")
        return [0.0] * horizon

    if len(series) < _MIN_HISTORY:
        logger.info(
            "select_forecast: series length %d < %d — using moving_average fallback",
            len(series),
            _MIN_HISTORY,
        )
        return moving_average(series, horizon=horizon)

    # ------------------------------------------------------------------ #
    # 2. Build candidate list                                              #
    # ------------------------------------------------------------------ #
    # Each entry: (display_name, model_callable_accepting_series_and_horizon)
    # Ordered most-sophisticated first so ties break in favour of simpler
    # models (last writer wins when MAPE scores are equal after sort).
    def _make_candidate(
        fn: Callable[..., list[float]], name: str
    ) -> tuple[str, Callable[[list[float]], list[float]]]:
        """Wrap fn so backtest() can call it as fn(train, horizon=n)."""
        def _wrapped(s: list[float], horizon: int = horizon) -> list[float]:
            return fn(s, horizon=horizon)
        _wrapped.__name__ = name  # for logging
        return name, _wrapped

    candidates: list[tuple[str, Callable[[list[float]], list[float]]]] = [
        _make_candidate(prophet_or_arima, "prophet_or_arima"),
        _make_candidate(holt_winters, "holt_winters"),
        _make_candidate(seasonal_naive, "seasonal_naive"),
        _make_candidate(moving_average, "moving_average"),  # guaranteed fallback
    ]

    # ------------------------------------------------------------------ #
    # 3. Backtest every candidate                                          #
    # ------------------------------------------------------------------ #
    scored: list[tuple[float, str, Callable[[list[float]], list[float]]]] = []

    for name, fn in candidates:
        score = backtest(fn, series)
        logger.debug("select_forecast: %s MAPE=%.4f", name, score)
        scored.append((score, name, fn))

    # ------------------------------------------------------------------ #
    # 4. Pick winner (lowest MAPE)                                         #
    # ------------------------------------------------------------------ #
    scored.sort(key=lambda t: t[0])
    best_mape, best_name, best_fn = scored[0]

    if best_mape == float("inf"):
        # Every model failed its backtest — use moving_average as the
        # unconditional fallback (it never raises).
        logger.warning(
            "select_forecast: all models returned inf MAPE — falling back to moving_average"
        )
        return moving_average(series, horizon=horizon)

    logger.info(
        "select_forecast: selected %s (MAPE=%.4f) for horizon=%d over series length=%d",
        best_name,
        best_mape,
        horizon,
        len(series),
    )

    # ------------------------------------------------------------------ #
    # 5. Train winner on full series and return predictions                #
    # ------------------------------------------------------------------ #
    try:
        return best_fn(series, horizon=horizon)
    except Exception as exc:  # noqa: BLE001
        logger.warning(
            "select_forecast: %s failed on full series (%s) — falling back to moving_average",
            best_name,
            exc,
        )
        return moving_average(series, horizon=horizon)
