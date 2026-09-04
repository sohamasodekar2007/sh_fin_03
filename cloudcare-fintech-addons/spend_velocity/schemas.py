from __future__ import annotations

from datetime import datetime, timezone
from typing import Literal
from uuid import uuid4

from pydantic import BaseModel, Field

Severity = Literal["low", "medium", "high", "critical"]

ContainmentAction = Literal[
    "monitor_only",
    "alert_only",
    "throttle_non_prod",
    "escalate_supervisor",
    "block_auto_execute",
]


class SpendSample(BaseModel):
    """One estimated-cost observation for a scope. `scope` is deliberately
    a free-form string, not an enum — it can be a resource id, an account,
    a tag value, an API key, or an agent name, matching whatever
    granularity the caller wants a circuit breaker on."""

    scope: str
    timestamp: datetime
    estimated_cost: float = Field(ge=0)
    is_production: bool = False
    tags: dict[str, str] = Field(default_factory=dict)


class VelocityReading(BaseModel):
    scope: str
    window_end: datetime
    baseline_hourly_rate: float = Field(ge=0)
    current_hourly_rate: float = Field(ge=0)
    # Ratio, not a raw slope — capped at 1_000_000 so this stays a normal
    # JSON float (never inf/nan) even for a brand-new, previously-zero
    # baseline; see detector.compute_velocity for the capping rule.
    velocity_ratio: float = Field(ge=0)
    sample_count: int = Field(ge=0)
    baseline_sample_count: int = Field(ge=0)
    # How much this reading should be trusted, purely a function of how
    # much baseline history exists — never a measure of statistical
    # significance of the spike itself. Low confidence means "not enough
    # history yet," not "this probably isn't real."
    confidence: float = Field(ge=0, le=1)


class VelocityAlert(BaseModel):
    alert_id: str = Field(default_factory=lambda: str(uuid4()))
    scope: str
    severity: Severity
    reading: VelocityReading
    recommended_action: ContainmentAction
    rationale: str
    requires_human_approval: bool
    projected_24h_cost: float = Field(ge=0)
    detected_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
