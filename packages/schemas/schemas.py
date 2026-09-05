"""
Core schemas, mirrored from the CloudCare blueprint (sections 3.2, 4.1, 6.2).
These are the contracts the frontend, the LangGraph orchestrator, and
MongoDB collections all agree on.
"""

from datetime import datetime
from decimal import Decimal
from typing import Any, Literal
from uuid import UUID, uuid4
from pydantic import BaseModel, Field, model_validator

# ---------------------------------------------------------------------------
# Shared / workflow state (blueprint 3.2)
# ---------------------------------------------------------------------------

class Evidence(BaseModel):
    metric: str
    value: float
    window_days: int


class CloudCareState(BaseModel):
    run_id: str
    tenant_id: str
    account_id: str
    observation: dict = Field(default_factory=dict)
    findings: list[dict] = Field(default_factory=list)
    proposals: list[dict] = Field(default_factory=list)
    approvals: list[dict] = Field(default_factory=list)
    execution_log: list[dict] = Field(default_factory=list)
    feedback: list[dict] = Field(default_factory=list)
    status: Literal["observing", "analyzing", "review", "executing", "verified", "halted"] = "observing"
    reanalysis_count: int = 0
    trace: list[dict] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Resources / inventory (blueprint 4.1)
# ---------------------------------------------------------------------------

ResourceStatus = Literal["Healthy", "Idle", "Over-provisioned", "At-risk"]


class Resource(BaseModel):
    id: str
    type: str
    region: str = "ap-south-1"
    cpu_p95: float
    status: ResourceStatus
    # None when this resource has no real FOCUS BilledCost yet (a genuinely
    # idle/new resource, or the live export hasn't billed it this period) —
    # never a fabricated flat estimate. See apps/api/routers/observation.py's
    # resource-sync step, which joins against the FOCUS dataset it just built.
    monthly_cost_usd: float | None = None
    cost_source: Literal["focus_live_export", "focus_synthesized", "focus_sample", "focus_modelled", "no_focus_row"] = "no_focus_row"
    focus_dataset_id: str | None = None
    focus_version: str | None = None
    focus_source: str | None = None
    focus_row_count: int = 0
    # "ec2_instance" | "ebs_volume" | provider-specific — lets the frontend
    # tell resource kinds apart by a real field instead of pattern-matching
    # the `type` string (which for EBS is a size/SKU label like "500GB-gp3").
    resource_type: str | None = None
    instance_type: str | None = None
    vcpu: int | None = None
    memory_gib: float | None = None
    provider: str | None = None
    state: str | None = None
    tags: dict[str, str] = Field(default_factory=dict)
    owner: str | None = None
    environment: Literal["dev", "staging", "prod"] = "dev"


# ---------------------------------------------------------------------------
# Proposals / recommendations (blueprint 6.2)
# ---------------------------------------------------------------------------

class ActionProposal(BaseModel):
    proposal_id: UUID = Field(default_factory=uuid4)
    resource_arn: str
    action_type: Literal[
        "stop_instance", "schedule_instance", "resize_instance", "delete_volume",
        # Phase 15 — an ASG-managed idle instance never gets a plain
        # stop_instance (AWS would just replace it); adjusts desired
        # capacity instead. no_action is an explicit "considered, declined"
        # outcome (termination-protected, or ASG already at its minimum) —
        # visible in the UI instead of the finding silently vanishing.
        "adjust_asg_capacity", "no_action",
    ]
    template_id: str
    parameters: dict = Field(default_factory=dict)
    expected_monthly_savings: Decimal
    risk_level: Literal["low", "medium", "high", "critical"]
    confidence: float = Field(ge=0, le=1)
    evidence: list[Evidence] = Field(default_factory=list)
    rollback_plan: dict | None = None
    requires_human_approval: bool = False
    # "pending_approval"/"blocked" are the Supervisor's outcomes (Phase 4/5
    # services/supervisor/service.py) — added here so GET /v1/recommendations
    # (response_model=list[ActionProposal]) doesn't 500 once a proposal
    # reaches either status.
    status: Literal[
        "proposed", "pending_approval", "approved", "rejected", "blocked", "executed", "verified"
    ] = "proposed"

    # Set when status transitions to "rejected" (see apps/api/routers/recommendations.py).
    # The Monitor agent uses this to resurface stale rejections after an hour — see
    # apps/api/routers/observation.py:_resurface_rejected_proposals().
    rejected_at: datetime | None = None
    # Set on a freshly-created proposal that resurfaces an older rejected one.
    supersedes_proposal_id: str | None = None

    # Which cloud this proposal's resource lives on. Drives the executor's
    # VPS refusal (services/executor/simulated_executor.py) — VPS is
    # read-only in this build.
    provider: Literal["aws", "azure", "gcp", "vps"] = "aws"

    # "billable" (default): a real invoice exists, so acting on this
    # proposal produces a real dollar saving. "reclaimable_capacity": a
    # fixed-price server (VPS) is owed its monthly cost regardless — see
    # services/focus/mappers/vps.py's module docstring. When set, this
    # proposal's expected_monthly_savings must be exactly 0 (enforced
    # below) and the real value lives in reclaimable_vcpu/reclaimable_memory_mb.
    savings_type: Literal["billable", "reclaimable_capacity"] = "billable"
    reclaimable_vcpu: float | None = None
    reclaimable_memory_mb: float | None = None

    @model_validator(mode="after")
    def _reclaimable_capacity_never_claims_dollar_savings(self) -> "ActionProposal":
        if self.savings_type == "reclaimable_capacity" and self.expected_monthly_savings != Decimal("0"):
            raise ValueError(
                "A reclaimable_capacity proposal (VPS) must have expected_monthly_savings == 0 — "
                "a fixed-price server's cost is owed regardless of what runs on it, so stopping "
                "something never produces a real dollar saving. Use reclaimable_vcpu / "
                "reclaimable_memory_mb to carry the real value instead."
            )
        return self


# ---------------------------------------------------------------------------
# Agent activity feed
# ---------------------------------------------------------------------------

AgentName = Literal["Monitor", "Analyzer", "Decision", "Supervisor", "Executor"]


class AgentActivityEntry(BaseModel):
    id: str
    agent: AgentName
    message: str
    timestamp: str
    # Additive (Phase 10) — the underlying agent_runs document
    # (services/agent_log.py) always has these; the API just didn't
    # surface them until the dashboard's AgentActivityFeed needed to show
    # per-run status/duration and an expandable payload.
    status: Literal["success", "failed"] = "success"
    duration_ms: int = 0
    payload: dict[str, Any] = Field(default_factory=dict)


# ---------------------------------------------------------------------------
# Forecast / savings
# ---------------------------------------------------------------------------

class ForecastPoint(BaseModel):
    date: str
    actual: float | None = None
    predicted: float | None = None


class SavingsSummary(BaseModel):
    total_monthly_spend: float
    wasted_spend_detected: float
    wasted_spend_pct: float
    savings_this_month: float
    resources_monitored: int


# ---------------------------------------------------------------------------
# Auth Models & 3FA
# ---------------------------------------------------------------------------

class LoginRequest(BaseModel):
    user_id: str
    password: str


class LoginBypassRequest(BaseModel):
    user_id: str
    password: str


class LoginResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user_id: str
    tenant_id: str


class LoginStep1Response(BaseModel):
    status: Literal["otp_required", "authenticated"]
    user_id: str
    temp_token: str | None = None
    access_token: str | None = None
    token_type: str = "bearer"
    tenant_id: str | None = None


class OtpVerifyRequest(BaseModel):
    temp_token: str
    otp: str


class OtpVerifyResponse(BaseModel):
    status: Literal["webauthn_required", "webauthn_registration_required"]
    user_id: str
    temp_token: str


class OtpResendRequest(BaseModel):
    temp_token: str


class WebAuthnRegisterBeginRequest(BaseModel):
    temp_token: str


class WebAuthnRegisterFinishRequest(BaseModel):
    temp_token: str
    registration_response: dict


class WebAuthnAuthenticateBeginRequest(BaseModel):
    temp_token: str


class WebAuthnAuthenticateFinishRequest(BaseModel):
    temp_token: str
    authentication_response: dict


class WebAuthnSessionRegisterFinishRequest(BaseModel):
    session_id: str
    registration_response: dict


class SsoMfaPreferenceRequest(BaseModel):
    mfa_level: Literal["none", "2fa", "3fa"]


class RegisterRequest(BaseModel):
    user_id: str
    password: str
    email: str
    tenant_id: str = "demo-tenant"
    full_name: str | None = None


class UserPublic(BaseModel):
    """Safe-to-return shape — never includes hashed_password."""
    user_id: str
    tenant_id: str
    email: str | None = None
    full_name: str | None = None


class SsoCallbackRequest(BaseModel):
    """Phase 9 — posted by the frontend's NextAuth v5 server-side callback
    after Google/GitHub completes the OAuth handshake. provider_account_id
    is the OAuth provider's own stable user id (never the CloudCare
    user_id), used to link repeat sign-ins deterministically."""
    provider: Literal["google", "github"]
    email: str
    name: str | None = None
    provider_account_id: str


class UserInDB(BaseModel):
    """Mirrors the `users` Mongo collection."""
    user_id: str
    tenant_id: str
    hashed_password: str
    email: str | None = None
    full_name: str | None = None


# ---------------------------------------------------------------------------
# CloudAccount (blueprint 4.1 — secure onboarding)
# ---------------------------------------------------------------------------

class CloudAccount(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid4()))
    tenant_id: str
    provider: Literal["aws", "gcp", "azure"] = "aws"
    account_id: str
    status: Literal["pending", "validated", "failed"] = "pending"

    # True once this provider has a real, validated live connection.
    # False means the Monitor agent serves FOCUS sample data for it instead
    # of pretending to observe a real account — see
    # services/focus/mappers/{gcp,azure,vps}.py.
    connected: bool = False

    # AWS specific
    role_arn: str | None = None
    external_id: str | None = None
    region: str = "ap-south-1"

    # GCP specific
    gcp_service_account_json: dict | None = None

    # Azure specific
    azure_tenant_id: str | None = None
    azure_client_id: str | None = None
    azure_client_secret: str | None = None
