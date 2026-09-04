"""
Core schemas, mirrored from the CloudCare blueprint (sections 3.2, 4.1, 6.2).
These are the contracts the frontend, the LangGraph orchestrator, and
MongoDB collections all agree on.
"""

from decimal import Decimal
from typing import Literal
from uuid import UUID, uuid4
from pydantic import BaseModel, Field

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
    monthly_cost_usd: float
    tags: dict[str, str] = Field(default_factory=dict)
    owner: str | None = None
    environment: Literal["dev", "staging", "prod"] = "dev"


# ---------------------------------------------------------------------------
# Proposals / recommendations (blueprint 6.2)
# ---------------------------------------------------------------------------

class ActionProposal(BaseModel):
    proposal_id: UUID = Field(default_factory=uuid4)
    resource_arn: str
    action_type: Literal["stop_instance", "schedule_instance", "resize_instance", "delete_volume"]
    template_id: str
    parameters: dict = Field(default_factory=dict)
    expected_monthly_savings: Decimal
    risk_level: Literal["low", "medium", "high", "critical"]
    confidence: float = Field(ge=0, le=1)
    evidence: list[Evidence] = Field(default_factory=list)
    rollback_plan: dict | None = None
    requires_human_approval: bool = False
    status: Literal["proposed", "approved", "rejected", "executed", "verified"] = "proposed"


# ---------------------------------------------------------------------------
# Agent activity feed
# ---------------------------------------------------------------------------

AgentName = Literal["Monitor", "Analyzer", "Decision", "Supervisor", "Executor"]


class AgentActivityEntry(BaseModel):
    id: str
    agent: AgentName
    message: str
    timestamp: str


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
