from datetime import datetime, timezone
from decimal import Decimal
from typing import Any, Literal
from uuid import uuid4

from pydantic import BaseModel, Field


Environment = Literal[
    "development",
    "staging",
    "production",
    "unknown",
]

RiskLevel = Literal[
    "low",
    "medium",
    "high",
]

PolicyOutcome = Literal[
    "auto_approved",
    "human_review",
    "blocked",
]


class ActionProposal(BaseModel):
    proposal_id: str = Field(
        default_factory=lambda: str(uuid4())
    )

    tenant_id: str
    snapshot_id: str
    resource_id: str
    resource_type: str

    action_template: str
    environment: Environment
    risk_level: RiskLevel

    rationale: str
    parameters: dict[str, Any] = Field(default_factory=dict)

    estimated_monthly_savings_usd: Decimal = Field(
        default=Decimal("0"),
        ge=0,
    )

    created_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc)
    )


class PolicyDecision(BaseModel):
    proposal_id: str
    outcome: PolicyOutcome

    reason_codes: list[str] = Field(default_factory=list)
    policy_version: str

    simulation_allowed: bool = False
    live_execution_allowed: bool = False

    evaluated_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc)
    )
