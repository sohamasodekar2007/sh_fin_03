"""Forecast-overage anomaly detection: "did today's actual cost land
significantly above what was predicted for it."

Deliberately distinct from the existing services/analyzer/rules.py
classify_spend_anomaly, which flags a day against a *trailing mean*
(z-score vs the last 14 days). This package flags a day against what a
forecast model actually predicted *for that specific day*, via
walk-forward evaluation — the two are complementary, not duplicates.

Standalone package — see ../MERGE_GUIDE.md for the merge step. On merge,
`baseline_forecast.py`'s simple forecaster should be replaced by
services.forecasting.select.select_forecast (the real backtested/
MAPE-selected model already in the main repo); it's reimplemented here in
a simplified form only so this addon has no dependency on that module's
heavier optional deps (statsmodels/Prophet).
"""

from .guard import ForecastAnomalyGuard
from .schemas import DailyCostPoint, ForecastComparison, ForecastSeverity

__all__ = ["ForecastAnomalyGuard", "DailyCostPoint", "ForecastComparison", "ForecastSeverity"]
