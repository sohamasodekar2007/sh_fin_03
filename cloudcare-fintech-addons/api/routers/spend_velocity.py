from __future__ import annotations

from fastapi import APIRouter
from pydantic import BaseModel

from demo.scenario import (
    SCENARIO_NOW,
    build_spend_spike_hourly_series,
    build_spend_spike_period_rates,
    build_spend_spike_scenario,
)
from spend_velocity.guard import SpendVelocityGuard
from spend_velocity.notify import NullNotificationSink
from spend_velocity.schemas import SpendSample, VelocityAlert

router = APIRouter(prefix="/spend-velocity", tags=["spend-velocity"])
_guard = SpendVelocityGuard(notification_sink=NullNotificationSink())


class EvaluateRequest(BaseModel):
    samples: list[SpendSample]
    is_production: bool = False
    baseline_period_rates: list[float] | None = None
    current_period_rates: list[float] | None = None


@router.get("/demo-alert", response_model=VelocityAlert | None)
def demo_alert(live: bool = False) -> VelocityAlert | None:
    """Runs the synthetic spend-spike scenario (see demo/scenario.py)
    through the guard and returns whatever alert it produces (or null).
    `live=true` anchors the scenario to the real wall clock and reseeds
    noise every 15s, so a polling dashboard sees gentle movement instead
    of a frozen snapshot."""
    samples = build_spend_spike_scenario(live=live)
    baseline_rates, current_rates = build_spend_spike_period_rates(live=live)
    return _guard.evaluate(
        samples,
        is_production=True,
        now=None if live else SCENARIO_NOW,
        baseline_period_rates=baseline_rates,
        current_period_rates=current_rates,
    )


@router.get("/demo-series")
def demo_series(live: bool = False, hours_back: int = 30) -> list[dict]:
    """Hourly cost buckets for the sparkline — real aggregation of the
    same scenario `/demo-alert` evaluates, not a separately-fabricated
    curve."""
    return build_spend_spike_hourly_series(live=live, hours_back=hours_back)


@router.post("/evaluate", response_model=VelocityAlert | None)
def evaluate(request: EvaluateRequest) -> VelocityAlert | None:
    """Real-usage endpoint: pass in your own SpendSample feed instead of
    the demo scenario."""
    return _guard.evaluate(
        request.samples,
        is_production=request.is_production,
        baseline_period_rates=request.baseline_period_rates,
        current_period_rates=request.current_period_rates,
    )
