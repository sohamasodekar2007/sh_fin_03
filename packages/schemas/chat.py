"""
Chatbot contracts (Phase 7) — the one schema the frontend renders against
for every generative-UI card, plus the session/request/response shapes for
apps/api/routers/chat.py. Built fresh for CHATBOT_ARCHITECTURE.md's
two-mode design (this repo's copy of that document was not found — see
services/chat/service.py's module docstring for what was reconstructed
from the Phase 7 prompt instead).
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Annotated, Any, Literal
from uuid import uuid4

from pydantic import BaseModel, Field

ChatMode = Literal["existing", "new"]
ChatRole = Literal["system", "user", "assistant", "tool"]


class ChatMessage(BaseModel):
    role: ChatRole
    content: str
    # Only set on role == "tool" (the tool_call_id it answers) or on an
    # assistant message that made tool calls.
    tool_call_id: str | None = None
    name: str | None = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


# ---------------------------------------------------------------------------
# Generative UI cards — one Pydantic model per card type, a tagged union so
# the frontend can switch on `type` with one contract for all four.
# ---------------------------------------------------------------------------


class ApprovalCard(BaseModel):
    """Never a side effect of the chat turn itself — approve_proposal only
    ever returns one of these. The click goes through the real Phase 5
    approval endpoints (apps/api/routers/supervisor.py), with real auth."""

    type: Literal["approval_card"] = "approval_card"
    proposal_id: str
    action: str
    target: str
    savings: float
    risk: str
    confidence: float


class FindingCard(BaseModel):
    type: Literal["finding_card"] = "finding_card"
    resource_id: str
    rule_id: str
    summary: str
    evidence: dict[str, Any] = Field(default_factory=dict)


class CostSummaryCard(BaseModel):
    type: Literal["cost_summary_card"] = "cost_summary_card"
    period_days: int
    total_cost_usd: float
    top_services: list[dict[str, Any]] = Field(default_factory=list)


class RecommendationOption(BaseModel):
    name: str
    estimated_monthly_cost_usd: float
    pros: list[str] = Field(default_factory=list)
    cons: list[str] = Field(default_factory=list)


class RecommendationCard(BaseModel):
    type: Literal["recommendation_card"] = "recommendation_card"
    summary: str
    estimated_monthly_cost_usd: float
    reasoning: str
    options: list[RecommendationOption] = Field(default_factory=list, min_length=2, max_length=3)


ChatCard = Annotated[
    ApprovalCard | FindingCard | CostSummaryCard | RecommendationCard,
    Field(discriminator="type"),
]


# ---------------------------------------------------------------------------
# Sessions
# ---------------------------------------------------------------------------


class ChatSession(BaseModel):
    session_id: str = Field(default_factory=lambda: str(uuid4()))
    tenant_id: str
    user_id: str
    messages: list[ChatMessage] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class ChatSessionCreateResponse(BaseModel):
    session_id: str


class ChatHistoryResponse(BaseModel):
    session_id: str
    messages: list[ChatMessage]


# ---------------------------------------------------------------------------
# Mode "new" — the intake form, validated server-side. The client's own
# validation (if any) is never trusted.
# ---------------------------------------------------------------------------


class NewWorkloadForm(BaseModel):
    company_size: Literal["startup", "smb", "mid_market", "enterprise"]
    monthly_budget: float = Field(gt=0, le=10_000_000)
    current_storage_platform: str = Field(min_length=1, max_length=200)
    workload_type: str = Field(min_length=1, max_length=200)
    compliance_needs: list[str] = Field(default_factory=list, max_length=20)
    growth_expectation: Literal["flat", "moderate", "high"]


# ---------------------------------------------------------------------------
# Request / response
# ---------------------------------------------------------------------------


class ChatMessageRequest(BaseModel):
    session_id: str
    mode: ChatMode
    content: str = Field(min_length=1, max_length=4000)
    form_data: NewWorkloadForm | None = None


class ChatMessageResponse(BaseModel):
    session_id: str
    role: Literal["assistant"] = "assistant"
    content: str
    cards: list[ChatCard] = Field(default_factory=list)
    tool_calls_made: list[str] = Field(default_factory=list)
