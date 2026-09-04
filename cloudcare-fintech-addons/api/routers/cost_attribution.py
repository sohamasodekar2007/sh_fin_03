from __future__ import annotations

from fastapi import APIRouter
from pydantic import BaseModel

from cost_attribution import CostBreakdown, CostSample, decompose
from demo.scenario import build_cost_attribution_scenario

router = APIRouter(prefix="/cost-attribution", tags=["cost-attribution"])


class DecomposeRequest(BaseModel):
    current: list[CostSample]
    baseline: list[CostSample]
    dimension_key: str
    top_n: int = 5


@router.get("/demo-breakdown", response_model=CostBreakdown)
def demo_breakdown() -> CostBreakdown:
    current, baseline = build_cost_attribution_scenario()
    return decompose(current, baseline, "merchant")


@router.post("/breakdown", response_model=CostBreakdown)
def breakdown(request: DecomposeRequest) -> CostBreakdown:
    return decompose(request.current, request.baseline, request.dimension_key, top_n=request.top_n)
