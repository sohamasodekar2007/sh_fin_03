"""
Backtesting utilities — blueprint §5.2.

mape:     Mean Absolute Percentage Error between predictions and actuals.
backtest: Walk-forward evaluation of a model function over a held-out tail.
"""

from __future__ import annotations

import logging
from typing import Callable

logger = logging.getLogger(__name__)

# Minimum observations needed to split into train + test sets.
_MIN_BACKTEST_LENGTH = 10
# Fraction of the series held out as the test window.
_TEST_FRACTION = 0.2


def mape(predictions: list[float], actuals: list[float]) -> float:
    """
    Mean Absolute Percentage Error (MAPE).

    Zero actuals are skipped to avoid division-by-zero.  Returns infinity
    when no valid pairs exist, so the caller can always compare MAPE values
    numerically.

    Args:
        predictions: Predicted values.
        actuals:     Observed values (same length as predictions).

    Returns:
        MAPE as a float in [0, ∞).  Lower is better.
    """
    if len(predictions) != len(actuals):
        raise ValueError(
            f"predictions length {len(predictions)} != actuals length {len(actuals)}"
        )

    valid_pairs = [
        abs(p - a) / abs(a)
        for p, a in zip(predictions, actuals)
        if a != 0.0
    ]

    if not valid_pairs:
        return float("inf")

    return round(sum(valid_pairs) / len(valid_pairs), 6)


def backtest(
    model_fn: Callable[[list[float]], list[float]],
    series: list[float],
) -> float:
    """
    Walk-forward backtest of `model_fn` over the held-out tail of `series`.

    Splits `series` into a training set (first 80%) and a test window
    (last 20%, minimum 1 day).  Trains on the training set, predicts
    len(test) steps, then returns MAPE against the test actuals.

    Returns infinity when the series is too short to split, so the caller
    can still compare models safely.

    Args:
        model_fn: A callable (list[float]) -> list[float] that accepts a
                  training series and returns predictions.  It must accept
                  an implicit `horizon` via closure or default argument.
        series:   Full historical series, oldest-first.

    Returns:
        MAPE score.  Lower is better.  Returns float('inf') on failure.
    """
    if len(series) < _MIN_BACKTEST_LENGTH:
        logger.debug(
            "backtest: series too short (%d < %d) — returning inf",
            len(series),
            _MIN_BACKTEST_LENGTH,
        )
        return float("inf")

    split = max(1, int(len(series) * (1 - _TEST_FRACTION)))
    train = series[:split]
    test = series[split:]

    if not train or not test:
        return float("inf")

    horizon = len(test)

    try:
        # Wrap model_fn so it always receives the correct horizon.
        predictions = model_fn(train, horizon=horizon)  # type: ignore[call-arg]
        return mape(predictions, test)
    except TypeError:
        # model_fn doesn't accept a horizon keyword — call without it and
        # truncate/pad the result.
        try:
            raw = model_fn(train)
            predictions = (raw + [raw[-1]] * horizon)[:horizon] if raw else [0.0] * horizon
            return mape(predictions, test)
        except Exception as exc:  # noqa: BLE001
            logger.warning("backtest: model_fn raised %s — returning inf", exc)
            return float("inf")
    except Exception as exc:  # noqa: BLE001
        logger.warning("backtest: model_fn raised %s — returning inf", exc)
        return float("inf")
