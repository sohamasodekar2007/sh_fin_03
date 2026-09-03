from datetime import datetime
from typing import Any, Literal
from uuid import uuid4

from pydantic import BaseModel, Field

from packages.schemas.cloud_metrics import DailyCost, EC2CpuMetric


class CollectionIssue(BaseModel):
    source: Literal["ec2", "cloudwatch", "cost_explorer"]
    error_type: str
    message: str
    retryable: bool = True


class CloudSnapshot(BaseModel):
    snapshot_id: str = Field(
        default_factory=lambda: str(uuid4())
    )

    account_id: str
    region: str
    collected_at: datetime

    status: Literal["success", "partial", "failed"]

    resource_count: int = 0
    metric_count: int = 0
    cost_day_count: int = 0

    resources: list[dict[str, Any]] = Field(default_factory=list)
    cpu_metrics: list[EC2CpuMetric] = Field(default_factory=list)
    daily_costs: list[DailyCost] = Field(default_factory=list)
    issues: list[CollectionIssue] = Field(default_factory=list)
