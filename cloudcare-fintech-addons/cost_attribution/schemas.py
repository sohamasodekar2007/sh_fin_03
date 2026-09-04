from __future__ import annotations

from pydantic import BaseModel, Field


class CostSample(BaseModel):
    """One cost observation attributed to a single dimension value —
    e.g. dimension_key="merchant", dimension_value="M-4082". Callers
    build one list per window (baseline vs current); a sample never
    carries both windows itself."""

    scope: str
    dimension_key: str
    dimension_value: str
    cost: float = Field(ge=0)


class Contributor(BaseModel):
    dimension_key: str
    dimension_value: str
    baseline_cost: float
    current_cost: float
    delta: float
    pct_of_total_delta: float


class CostBreakdown(BaseModel):
    scope: str
    dimension_key: str
    baseline_total: float
    current_total: float
    total_delta: float
    contributors: list[Contributor]
    unattributed_delta: float
    unattributed_pct: float
    rationale: str
