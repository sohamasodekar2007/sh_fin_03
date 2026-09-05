from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

ForecastSeverity = Literal["normal", "watch", "warning", "critical"]


class DailyCostPoint(BaseModel):
    """One day's actual landed cost. `date` is an ISO date string
    (YYYY-MM-DD) — kept as a plain string rather than a `date` object so
    this survives a JSON round-trip through the API with no
    serialization surprises, matching the rest of this addon's schemas."""

    date: str
    actual_cost: float = Field(ge=0)


class ForecastComparison(BaseModel):
    """Only ever built by detector.compare_to_forecast. `overage_pct` can
    be negative (actual came in under the forecast) — that's never
    flagged as an anomaly, since the whole point here is catching cost
    that exceeded prediction, not celebrating savings via the same
    field."""

    date: str
    predicted_cost: float
    actual_cost: float
    overage_pct: float
    severity: ForecastSeverity
    is_anomaly: bool
    rationale: str
