"""
Phase 14's own schemas — deliberately NOT ActionProposal (either the one in
packages/schemas/schemas.py or the older one in packages/schemas/policy.py).
RDS/S3 recommendations and IAM security findings must never enter the real
executable-proposal pipeline; giving them a disjoint shape makes that a
structural fact (nothing in services/executor/actions.py's dispatch table
or services/executor/registry.py's ACTION_REGISTRY has ever heard of these
types), not a convention someone could accidentally violate later.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Literal

from pydantic import BaseModel, Field
from uuid import uuid4


class SecurityFinding(BaseModel):
    """An IAM posture finding — audit only. No cost field, no execution
    field, no status field that could ever mean "approved" or "executed."""

    finding_id: str = Field(default_factory=lambda: str(uuid4()))
    rule_id: str
    severity: Literal["low", "medium", "high", "critical"]
    principal_type: Literal["user", "role"]
    principal_name: str
    principal_arn: str | None = None
    policy_name: str
    policy_type: Literal["managed", "inline"]
    summary: str
    evidence: dict[str, Any] = Field(default_factory=dict)
    detected_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class RDSRecommendation(BaseModel):
    """Recommend-only, always. requires_human_approval is a hardcoded
    Literal[True], not a bool default — there is no way to construct one
    that claims auto-approval, even by a future bug."""

    resource_id: str
    db_instance_class: str
    region: str
    environment: str
    finding: Literal["idle_candidate"]
    confidence: float = Field(ge=0, le=1)
    current_monthly_cost: float | None = None
    evidence: dict[str, Any] = Field(default_factory=dict)
    # Always states the 7-day AWS auto-restart behavior explicitly — see
    # services/phase14/rds_advisor.py's docstring for why this can't be
    # silently omitted.
    rationale: str
    requires_human_approval: Literal[True] = True


class S3Recommendation(BaseModel):
    """Lifecycle-suggestion-only. No delete, no ACL/policy field exists on
    this model at all — there is nothing here an execution path could even
    misinterpret as a mutating permission."""

    bucket: str
    region: str
    current_storage_class: str
    suggested_storage_class: str
    evidence: dict[str, Any] = Field(default_factory=dict)
    rationale: str
    requires_human_approval: Literal[True] = True


class Phase14SectionError(BaseModel):
    """One section's collection failure — never propagates into a 500 for
    the other two sections. Same discipline as governance.py's `errors`
    dict."""

    section: str
    message: str
