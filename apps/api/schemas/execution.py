from datetime import datetime, timezone
from typing import Any, Literal
from uuid import uuid4

from pydantic import BaseModel, Field


ExecutionStatus = Literal[
    "simulated",
    "disabled",
    "blocked",
    "failed",
]


class ExecutionRecord(BaseModel):
    execution_id: str = Field(
        default_factory=lambda: str(uuid4())
    )

    idempotency_key: str
    proposal_id: str
    tenant_id: str

    resource_id: str
    resource_type: str
    environment: str
    action_template: str

    status: ExecutionStatus
    reason_codes: list[str] = Field(default_factory=list)

    policy_version: str

    would_execute: dict[str, Any] = Field(
        default_factory=dict
    )

    actual_aws_call_made: Literal[False] = False

    verification: dict[str, Any] = Field(
        default_factory=dict
    )

    requested_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc)
    )

    completed_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc)
    )
