from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

Pillar = Literal["cost_optimization", "security", "fault_tolerance", "service_limits"]
Grade = Literal["A", "B", "C", "D", "F"]


class ServiceUsageSample(BaseModel):
    service: str
    resource_count: int = Field(ge=0)
    monthly_cost: float = Field(ge=0)


class UnapprovedServiceFinding(BaseModel):
    service: str
    resource_count: int
    monthly_cost: float
    rationale: str


class TrustedServicesReport(BaseModel):
    approved_services: list[str]
    unapproved: list[UnapprovedServiceFinding]
    unapproved_cost: float
    unapproved_pct: float
    total_cost: float
    rationale: str


class PillarScore(BaseModel):
    pillar: Pillar
    score: float = Field(ge=0, le=100)
    finding_count: int
    critical_count: int
    rationale: str


class TrustScorecard(BaseModel):
    pillars: list[PillarScore]
    overall_score: float
    overall_grade: Grade
    rationale: str
