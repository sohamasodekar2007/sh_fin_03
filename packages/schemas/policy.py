"""
Decision + Supervisor Agent contracts (spec sections 4.3-4.4).

`ActionProposal` is the single canonical shape produced by the Decision
Agent (services/decision/service.py, optionally LLM-authored via
services/decision/llm.py) and consumed by the Supervisor's PolicyAdapter
and the Executor's SimulatedExecutor — every other layer (chat, REST
routers, frontend) reads/writes this same shape rather than each keeping
its own proposal schema, which is what actually keeps this pipeline from
turning into spaghetti.
"""

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
    proposal_id: str = Field(default_factory=lambda: str(uuid4()))

    tenant_id: str
    snapshot_id: str
    resource_id: str
    resource_type: str
    provider: Literal["aws", "gcp", "azure", "onprem"] = "aws"

    action_template: str  # e.g. "ec2.stop.v1" — see services/executor/registry.py::ACTION_REGISTRY
    environment: Environment
    risk_level: RiskLevel

    rationale: str
    parameters: dict[str, Any] = Field(default_factory=dict)

    estimated_monthly_savings_usd: Decimal = Field(default=Decimal("0"), ge=0)
    confidence: float = Field(default=0.75, ge=0, le=1)
    status: Literal["proposed", "approved", "rejected", "executed", "verified"] = "proposed"

    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class PolicyDecision(BaseModel):
    proposal_id: str
    outcome: PolicyOutcome

    # Continuous 0.0-1.0 risk score (spec section 4): < 0.3 -> AUTO_APPROVE,
    # >= 0.3 -> REQUIRE_HUMAN, 1.0 reserved for hard BLOCKED conditions
    # (protected tag, unknown action template).
    risk_score: float = Field(ge=0.0, le=1.0)

    reason_codes: list[str] = Field(default_factory=list)
    reason: str
    policy_version: str

    simulation_allowed: bool = False
    live_execution_allowed: bool = False

    evaluated_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc)
    )
