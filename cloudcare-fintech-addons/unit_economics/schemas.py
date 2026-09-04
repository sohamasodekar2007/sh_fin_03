from __future__ import annotations

from pydantic import BaseModel, Field


class BusinessMetricSample(BaseModel):
    """One period's cost + business-activity + (optional) revenue for a
    scope. `revenue` is optional and explicitly nullable — a scope with
    no revenue data must produce no margin claim, never a fabricated one."""

    scope: str
    period: str
    metric_name: str
    metric_value: float = Field(gt=0)
    cost: float = Field(ge=0)
    revenue: float | None = Field(default=None, ge=0)


class UnitCostResult(BaseModel):
    scope: str
    period: str
    metric_name: str
    cost_per_unit: float
    metric_value: float
    total_cost: float


class MarginResult(BaseModel):
    scope: str
    period: str
    revenue: float
    cost: float
    gross_margin_pct: float
    is_negative_margin: bool
    rationale: str
