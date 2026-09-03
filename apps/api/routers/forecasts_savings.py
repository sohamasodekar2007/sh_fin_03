"""GET /v1/forecasts, GET /v1/savings — cost-trend chart + KPI cards."""

from __future__ import annotations

from fastapi import APIRouter, Depends

from apps.api import mock_data
from apps.api.dependencies import get_current_user
from apps.api.pipeline import get_last_run
from packages.schemas.schemas import UserInDB

router = APIRouter(prefix="/v1", tags=["forecasts"])


@router.get("/forecasts")
async def forecasts(user: UserInDB = Depends(get_current_user)):
    run = get_last_run(user.tenant_id)
    daily_costs = run.get("observation", {}).get("daily_costs") if run else None
    if not daily_costs:
        return [p.model_dump() for p in mock_data.FORECAST]

    from services.forecasting.select import select_forecast

    history_points = [{"date": f"Day {i + 1}", "actual": cost} for i, cost in enumerate(daily_costs)]
    predicted = select_forecast(daily_costs, horizon=5)
    forecast_points = [{"date": f"Day {len(daily_costs) + i + 1}", "predicted": value} for i, value in enumerate(predicted)]
    return history_points + forecast_points


@router.get("/savings")
async def savings(user: UserInDB = Depends(get_current_user)):
    run = get_last_run(user.tenant_id)
    if not run:
        return mock_data.SAVINGS_SUMMARY.model_dump()

    observation = run.get("observation", {})
    resources = observation.get("resources", [])
    feedback = run.get("feedback", [])
    total_monthly_spend = round(sum(r.get("effective_cost", 0) for r in resources) * 30, 2)
    savings_this_month = round(sum(f.get("realized_monthly_savings_usd", 0) for f in feedback), 2)
    wasted = round(sum(float(p.get("estimated_monthly_savings_usd", 0)) for p in run.get("proposals", [])), 2)

    return {
        "total_monthly_spend": total_monthly_spend,
        "wasted_spend_detected": wasted,
        "wasted_spend_pct": round((wasted / total_monthly_spend) * 100, 1) if total_monthly_spend else 0,
        "savings_this_month": savings_this_month,
        "resources_monitored": len(resources),
    }
