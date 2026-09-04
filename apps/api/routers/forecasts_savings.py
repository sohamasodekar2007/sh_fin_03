"""
Forecasts & Savings router — blueprint §5.2.

GET /v1/forecasts
    Pulls daily cost records from the `cost_records` MongoDB collection
    (seeded on first request with realistic synthetic data).  Runs
    select_forecast() from the forecasting service to produce predictions.
    Returns a list[ForecastPoint] — actuals for past days, predicted for
    future days.

GET /v1/savings
    Returns a SavingsSummary.  Still sourced from mock_data; replace with
    real Feedback aggregation once the Verifier track is wired in.
"""

from __future__ import annotations

import logging
import math
import random
from datetime import date, timedelta

from fastapi import APIRouter, Depends, HTTPException

from apps.api.db import get_db
from apps.api.mock_data import SAVINGS_SUMMARY
from packages.schemas.schemas import ForecastPoint, SavingsSummary
from apps.api.dependencies import get_current_user
from services.forecasting import select_forecast

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/v1", tags=["forecasts-savings"])

# ---------------------------------------------------------------------------
# Seed helpers
# ---------------------------------------------------------------------------

_SEED_DAYS = 30          # days of synthetic history to seed
_FORECAST_HORIZON = 14   # days ahead to predict


def _generate_seed_series(n_days: int = _SEED_DAYS) -> list[dict]:
    """
    Generate `n_days` of realistic-looking daily cost records with a
    slight downward trend (simulating cost-optimisation wins) + weekly
    seasonality + small noise.

    Stored as {"date": "YYYY-MM-DD", "cost_usd": float} documents.
    """
    random.seed(42)          # reproducible seed so reruns are stable
    base_cost = 480.0
    trend_per_day = -3.0     # ~$90 drop over 30 days
    weekly_pattern = [1.05, 1.02, 1.00, 0.98, 0.96, 0.94, 0.97]  # Mon-Sun
    today = date.today()

    records = []
    for i in range(n_days):
        day = today - timedelta(days=(n_days - 1 - i))
        seasonal = weekly_pattern[day.weekday()]
        noise = random.gauss(0, 8)
        cost = max(0.0, base_cost + trend_per_day * i + noise) * seasonal
        records.append({"date": day.isoformat(), "cost_usd": round(cost, 2)})
    return records


async def _get_cost_series() -> list[dict]:
    """
    Return daily cost records from MongoDB, seeding the collection the
    first time it's empty so the demo always has data to forecast against.
    """
    db = get_db()
    if await db.cost_records.count_documents({}) == 0:
        seed_docs = _generate_seed_series(_SEED_DAYS)
        await db.cost_records.insert_many(seed_docs)
        logger.info("cost_records: seeded %d synthetic daily records", len(seed_docs))

    docs = (
        await db.cost_records
        .find({}, {"_id": 0, "date": 1, "cost_usd": 1})
        .sort("date", 1)
        .to_list(length=None)
    )
    return docs


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@router.get("/forecasts", response_model=list[ForecastPoint])
async def get_forecast(current_user: dict = Depends(get_current_user)) -> list[ForecastPoint]:
    """
    Return historical actuals + model-predicted future points.

    - Actuals come from the `cost_records` collection (seeded if empty).
    - Predictions are produced by select_forecast() (blueprint §5.2):
      it backtests moving_average, seasonal_naive, holt_winters, and
      prophet_or_arima, then returns the lowest-MAPE winner.
    - Falls back gracefully when history is under 14 days.
    """
    try:
        docs = await _get_cost_series()
    except Exception as exc:
        logger.error("get_forecast: DB error — %s", exc)
        raise HTTPException(status_code=503, detail="Cost data unavailable") from exc

    if not docs:
        return []

    # Extract ordered series of floats for the forecasting module.
    series: list[float] = [float(d["cost_usd"]) for d in docs]

    # Run model selection.
    predictions = select_forecast(series, horizon=_FORECAST_HORIZON)

    # Build ForecastPoint list: actuals first, then predicted.
    result: list[ForecastPoint] = []

    for doc in docs:
        result.append(ForecastPoint(date=doc["date"], actual=float(doc["cost_usd"])))

    last_date = date.fromisoformat(docs[-1]["date"])
    for i, pred_value in enumerate(predictions, start=1):
        future_date = (last_date + timedelta(days=i)).isoformat()
        result.append(ForecastPoint(date=future_date, predicted=round(pred_value, 2)))

    return result


@router.get("/savings", response_model=SavingsSummary)
async def get_savings_summary(current_user: dict = Depends(get_current_user)) -> SavingsSummary:
    """
    TODO: compute from verified Feedback documents (blueprint 4.1) —
    baseline cost minus post-action normalised cost, summed per
    tenant/account.  Returns mock data until that track is wired in.
    """
    return SAVINGS_SUMMARY
