"""
Core schemas, mirrored from the CloudCare blueprint (sections 3.2, 4.1, 6.2).
These are the contracts the frontend, the LangGraph orchestrator, and
MongoDB collections all agree on.

The canonical ActionProposal / PolicyDecision live in
packages/schemas/policy.py (they carry the Supervisor's PolicyAdapter and
Executor's SimulatedExecutor along with them) — not duplicated here.
"""

from datetime import datetime, timezone
from typing import Literal
from uuid import uuid4
from pydantic import BaseModel, Field

# ---------------------------------------------------------------------------
# Shared / workflow state (blueprint 3.2)
# ---------------------------------------------------------------------------

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
# Agent activity feed
# ---------------------------------------------------------------------------

AgentName = Literal["Monitor", "Analyzer", "Decision", "Supervisor", "Executor", "Verifier"]


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
# Auth — SSO trust model (spec section 2)
# ---------------------------------------------------------------------------
# FastAPI never mints or verifies passwords itself. NextAuth is the identity
# authority: OAuth (Google/GitHub/Microsoft Entra ID) or its own
# CredentialsProvider (bcrypt against the `users` Mongo collection) mints an
# HS256 JWT signed with NEXTAUTH_SECRET. FastAPI only decodes + auto-provisions.

AuthProvider = Literal["google", "github", "microsoft-entra-id", "credentials"]


class UserPublic(BaseModel):
    """Safe-to-return shape — never includes hashed_password."""
    id: str
    tenant_id: str
    email: str
    full_name: str | None = None
    image: str | None = None
    provider: AuthProvider


class UserInDB(BaseModel):
    """Mirrors the `users` Mongo collection. Auto-provisioned by FastAPI
    (see apps/api/dependencies.py::get_current_user) the first time a valid
    NextAuth JWT arrives for an email not yet seen, or created directly by
    NextAuth's CredentialsProvider on manual sign-up."""

    id: str = Field(default_factory=lambda: str(uuid4()))
    tenant_id: str = "demo-tenant"
    email: str
    full_name: str | None = None
    image: str | None = None

    provider: AuthProvider
    provider_account_id: str | None = None  # google `sub`, github `id`, entra `oid`
    hashed_password: str | None = None  # only set for provider == "credentials"

    created_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


# ---------------------------------------------------------------------------
# CloudAccount — multi-cloud onboarding (spec section 3)
# ---------------------------------------------------------------------------

class CloudAccount(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid4()))
    tenant_id: str
    provider: Literal["aws", "gcp", "azure", "onprem"]
    display_name: str
    account_id: str  # AWS account id / GCP project id / Azure subscription id / hostname

    # AWS
    role_arn: str | None = None
    external_id: str | None = None

    # GCP / Azure / on-prem — the raw secret (service-account JSON, client
    # secret, SSH key) is never stored; only its AES-256-GCM ciphertext is
    # (see services/adapters/crypto.py). `encrypted_credentials` holds
    # base64(nonce || ciphertext || tag).
    encrypted_credentials: str | None = None

    region: str = "us-east-1"
    status: Literal["pending", "validated", "failed"] = "pending"
    last_synced_at: str | None = None
