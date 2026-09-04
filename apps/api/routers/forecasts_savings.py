"""
Forecasts and savings router.

GET /v1/forecasts reads daily cost records from MongoDB when available and
falls back to deterministic demo history in development when Mongo is down.
GET /v1/savings returns the existing mock savings summary.
"""

from __future__ import annotations

import logging
import random
from datetime import date, timedelta

from fastapi import APIRouter, Depends, HTTPException

from apps.api.config import get_settings
from apps.api.db import get_db, mongo_available
from apps.api.dependencies import get_current_user
from apps.api.mock_data import SAVINGS_SUMMARY
from packages.schemas.schemas import ForecastPoint, SavingsSummary
from services.forecasting import select_forecast

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/v1", tags=["forecasts-savings"])

_SEED_DAYS = 30
_FORECAST_HORIZON = 14


def _generate_seed_series(n_days: int = _SEED_DAYS) -> list[dict]:
    random.seed(42)
    base_cost = 480.0
    trend_per_day = -3.0
    weekly_pattern = [1.05, 1.02, 1.00, 0.98, 0.96, 0.94, 0.97]
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


@router.get("/forecasts", response_model=list[ForecastPoint])
async def get_forecast(current_user: dict = Depends(get_current_user)) -> list[ForecastPoint]:
    if not await mongo_available():
        if get_settings().app_env != "development":
            raise HTTPException(status_code=503, detail="Cost data unavailable")
        docs = _generate_seed_series(_SEED_DAYS)
    else:
        try:
            docs = await _get_cost_series()
        except Exception as exc:
            logger.error("get_forecast: DB error - %s", exc)
            if get_settings().app_env != "development":
                raise HTTPException(status_code=503, detail="Cost data unavailable") from exc
            docs = _generate_seed_series(_SEED_DAYS)

    if not docs:
        return []

    series: list[float] = [float(d["cost_usd"]) for d in docs]
    predictions = select_forecast(series, horizon=_FORECAST_HORIZON)

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
    return SAVINGS_SUMMARY
