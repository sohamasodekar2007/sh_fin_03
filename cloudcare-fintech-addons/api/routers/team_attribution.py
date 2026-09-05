from __future__ import annotations

from fastapi import APIRouter
from pydantic import BaseModel

from demo.scenario import build_team_attribution_scenario
from team_attribution import TaggedResourceSample, TeamAttributionReport, aggregate_by_team

router = APIRouter(prefix="/team-attribution", tags=["team-attribution"])


class AggregateRequest(BaseModel):
    resources: list[TaggedResourceSample]
    tag_key: str = "team"


@router.get("/demo-report", response_model=TeamAttributionReport)
def demo_report(tag_key: str = "team") -> TeamAttributionReport:
    resources = [TaggedResourceSample(**r) for r in build_team_attribution_scenario()]
    return aggregate_by_team(resources, tag_key=tag_key)


@router.post("/report", response_model=TeamAttributionReport)
def report(request: AggregateRequest) -> TeamAttributionReport:
    return aggregate_by_team(request.resources, tag_key=request.tag_key)
