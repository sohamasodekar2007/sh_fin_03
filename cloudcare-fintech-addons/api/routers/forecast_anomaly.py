from __future__ import annotations

from fastapi import APIRouter
from pydantic import BaseModel

from demo.scenario import build_daily_cost_history
from forecast_anomaly.guard import ForecastAnomalyGuard
from forecast_anomaly.schemas import DailyCostPoint, ForecastComparison

router = APIRouter(prefix="/forecast-anomaly", tags=["forecast-anomaly"])
_guard = ForecastAnomalyGuard()


class EvaluateRequest(BaseModel):
    history: list[DailyCostPoint]
    watch_pct: float = 10.0
    warning_pct: float = 25.0
    critical_pct: float = 50.0
    evaluate_last_n_days: int = 7


@router.get("/demo-series", response_model=list[ForecastComparison])
def demo_series() -> list[ForecastComparison]:
    history = [DailyCostPoint(**p) for p in build_daily_cost_history()]
    return _guard.evaluate(history)


@router.post("/evaluate", response_model=list[ForecastComparison])
def evaluate(request: EvaluateRequest) -> list[ForecastComparison]:
    guard = ForecastAnomalyGuard(
        watch_pct=request.watch_pct,
        warning_pct=request.warning_pct,
        critical_pct=request.critical_pct,
        evaluate_last_n_days=request.evaluate_last_n_days,
    )
    return guard.evaluate(request.history)
