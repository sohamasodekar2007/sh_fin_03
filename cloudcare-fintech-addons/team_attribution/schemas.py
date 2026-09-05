from __future__ import annotations

from pydantic import BaseModel, Field


class TaggedResourceSample(BaseModel):
    resource_id: str
    resource_type: str
    environment: str | None = None
    monthly_cost: float = Field(ge=0)
    tags: dict[str, str] = Field(default_factory=dict)


class TeamCostSummary(BaseModel):
    team: str
    resource_count: int = Field(ge=0)
    total_monthly_cost: float
    environments: list[str]


class UntaggedResource(BaseModel):
    resource_id: str
    resource_type: str
    monthly_cost: float
    environment: str | None


class TeamAttributionReport(BaseModel):
    tag_key: str
    teams: list[TeamCostSummary]
    untagged_resources: list[UntaggedResource]
    untagged_cost: float
    untagged_pct: float
    total_cost: float
    rationale: str
