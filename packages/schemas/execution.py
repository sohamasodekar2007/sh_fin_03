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


# ---------------------------------------------------------------------------
# Real Executor (Phase 6) — services/executor/actions.py
#
# A DELIBERATELY SEPARATE model from ExecutionRecord above, not a relaxed
# version of it. ExecutionRecord's actual_aws_call_made is pinned to
# Literal[False] as a schema-level guarantee that SimulatedExecutor
# (services/executor/simulated_executor.py) can never claim to have made a
# real AWS call — see tests/unit/test_simulated_executor.py's
# test_execution_record_rejects_true_aws_call_flag. LiveExecutionRecord is
# the one place actual_aws_call_made is allowed to be True, and it is only
# ever constructed by services/executor/actions.py after every one of the
# three mandatory gates has passed.
# ---------------------------------------------------------------------------

LiveExecutionStatus = Literal[
    "executed",
    "no_op",
    "rejected",
    "rolled_back",
    "verification_failed",
    "refused",
    "failed",
]


class LiveExecutionRecord(BaseModel):
    execution_id: str = Field(default_factory=lambda: str(uuid4()))

    idempotency_key: str
    proposal_id: str
    tenant_id: str
    run_id: str | None = None

    resource_arn: str
    resource_id: str
    action_type: str
    step: str = "main"  # resize_instance writes one record per sub-step: stop / modify_type / start

    status: LiveExecutionStatus
    reason_codes: list[str] = Field(default_factory=list)

    execution_mode: Literal["simulation", "live"] = "simulation"
    actual_aws_call_made: bool = False

    before_state: dict[str, Any] = Field(default_factory=dict)
    after_state: dict[str, Any] = Field(default_factory=dict)

    rollback_descriptor: dict[str, Any] | None = None

    verification: dict[str, Any] = Field(default_factory=dict)

    started_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    completed_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
