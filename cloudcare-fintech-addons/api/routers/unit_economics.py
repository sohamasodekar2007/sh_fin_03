from __future__ import annotations

from fastapi import APIRouter
from pydantic import BaseModel

from demo.scenario import build_unit_economics_scenario
from unit_economics.engine import compute_margin, flag_negative_margin_scopes
from unit_economics.schemas import BusinessMetricSample, MarginResult

router = APIRouter(prefix="/unit-economics", tags=["unit-economics"])


class MarginsRequest(BaseModel):
    samples: list[BusinessMetricSample]
    threshold_pct: float = 0.0


class DemoSummary(BaseModel):
    all_margins: list[MarginResult]
    negative_margins: list[MarginResult]


@router.get("/demo-summary", response_model=DemoSummary)
def demo_summary() -> DemoSummary:
    samples = build_unit_economics_scenario()
    all_margins = [m for m in (compute_margin(s) for s in samples) if m is not None]
    negatives = flag_negative_margin_scopes(samples)
    return DemoSummary(all_margins=all_margins, negative_margins=negatives)


@router.post("/margins", response_model=list[MarginResult])
def margins(request: MarginsRequest) -> list[MarginResult]:
    return [m for m in (compute_margin(s, negative_margin_threshold_pct=request.threshold_pct) for s in request.samples) if m is not None]
