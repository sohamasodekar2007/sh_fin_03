"""
Advanced forecasting models — blueprint §5.2.

holt_winters:     Requires statsmodels; needs at least 2 full seasonal
                  cycles (≥14 days with period=7).
prophet_or_arima: Gated behind len(series) >= 90; uses statsmodels ARIMA
                  as the local implementation (Prophet requires an extra
                  heavy dependency).  Falls back to holt_winters when the
                  gate condition isn't met.
"""

from __future__ import annotations

import logging

from services.forecasting.baseline import moving_average

logger = logging.getLogger(__name__)

# Minimum series lengths required by each model.
_MIN_HOLT_WINTERS = 14   # 2 × weekly period
_MIN_ARIMA = 90          # blueprint §5.2 gate condition


def holt_winters(series: list[float], horizon: int = 30, period: int = 7) -> list[float]:
    """
    Exponential smoothing with trend + seasonal components (additive).

    Requires statsmodels and at least `_MIN_HOLT_WINTERS` observations.
    Falls back to moving_average when the gate condition is not met or
    when statsmodels is unavailable.

    Args:
        series:  Historical daily cost observations, oldest-first.
        horizon: Number of future days to predict.
        period:  Seasonal period in days (default 7 = weekly).

    Returns:
        List of `horizon` predicted float values.
    """
    if len(series) < _MIN_HOLT_WINTERS:
        logger.warning(
            "holt_winters: series length %d < minimum %d — falling back to moving_average",
            len(series),
            _MIN_HOLT_WINTERS,
        )
        return moving_average(series, horizon=horizon)

    try:
        from statsmodels.tsa.holtwinters import ExponentialSmoothing  # type: ignore

        model = ExponentialSmoothing(
            series,
            trend="add",
            seasonal="add",
            seasonal_periods=period,
            initialization_method="estimated",
        )
        fit = model.fit(optimized=True, disp=False)
        forecast = fit.forecast(horizon)
        # Clip negative predictions — costs can't be negative.
        return [round(max(float(v), 0.0), 4) for v in forecast]

    except ImportError:
        logger.warning("statsmodels not installed — falling back to moving_average")
        return moving_average(series, horizon=horizon)
    except Exception as exc:  # noqa: BLE001
        logger.warning("holt_winters fitting failed (%s) — falling back to moving_average", exc)
        return moving_average(series, horizon=horizon)


def prophet_or_arima(series: list[float], horizon: int = 30) -> list[float]:
    """
    ARIMA-based forecast, gated behind len(series) >= 90 (blueprint §5.2).

    Uses statsmodels ARIMA(1,1,1) with a seasonal ARIMA component when
    enough data is available.  Falls back to holt_winters when the gate
    condition is not met.

    Args:
        series:  Historical daily cost observations, oldest-first.
        horizon: Number of future days to predict.

    Returns:
        List of `horizon` predicted float values.
    """
    if len(series) < _MIN_ARIMA:
        logger.info(
            "prophet_or_arima: series length %d < gate %d — delegating to holt_winters",
            len(series),
            _MIN_ARIMA,
        )
        return holt_winters(series, horizon=horizon)

    try:
        from statsmodels.tsa.arima.model import ARIMA  # type: ignore

        model = ARIMA(series, order=(1, 1, 1))
        fit = model.fit()
        forecast = fit.forecast(steps=horizon)
        return [round(max(float(v), 0.0), 4) for v in forecast]

    except ImportError:
        logger.warning("statsmodels not installed — falling back to holt_winters")
        return holt_winters(series, horizon=horizon)
    except Exception as exc:  # noqa: BLE001
        logger.warning("prophet_or_arima fitting failed (%s) — falling back to holt_winters", exc)
        return holt_winters(series, horizon=horizon)
