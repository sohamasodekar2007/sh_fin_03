"""
Contracts for the chat orchestrator (spec section 5) — the request/response
shapes for POST /v1/chat, and the Generative UI approval-card payload the
Next.js chat window renders inline when the Supervisor Agent routes a
proposal to REQUIRE_HUMAN.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Literal
from uuid import uuid4

from pydantic import BaseModel, Field


class ChatMessage(BaseModel):
    role: Literal["user", "assistant", "tool"]
    content: str


class ChatRequest(BaseModel):
    messages: list[ChatMessage]
    tenant_id: str = "demo-tenant"


class ApprovalCardPayload(BaseModel):
    """Rendered by <ApprovalCard /> in the chat window. Approve/Reject post
    straight to the Executor via POST /v1/recommendations/{proposal_id}/decision."""

    type: Literal["approval_card"] = "approval_card"
    proposal_id: str
    resource_id: str
    action_template: str
    rationale: str
    estimated_monthly_savings_usd: float
    risk_score: float
    risk_reason: str


class ChatResponse(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid4()))
    role: Literal["assistant"] = "assistant"
    content: str
    ui: ApprovalCardPayload | None = None
    tool_called: str | None = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class AgentTraceEvent(BaseModel):
    """One entry broadcast over the /ws/agent-feed WebSocket and stored in
    CloudCareState.trace — this is what drives the frontend Agent Activity
    feed live instead of via polling."""

    agent: str
    at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    summary: dict[str, Any] = Field(default_factory=dict)
