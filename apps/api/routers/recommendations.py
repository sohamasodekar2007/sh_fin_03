"""
GET /v1/recommendations — proposals + the Supervisor's verdict on each.
POST /v1/recommendations/{proposal_id}/decision — the endpoint the chat
window's Generative UI <ApprovalCard/> Approve/Reject buttons call
(spec section 5) to push a REQUIRE_HUMAN proposal through the Executor.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel

from apps.api.dependencies import get_current_user
from apps.api.pipeline import get_last_run
from packages.schemas.policy import ActionProposal, PolicyDecision
from packages.schemas.schemas import UserInDB

router = APIRouter(prefix="/v1", tags=["recommendations"])


@router.get("/recommendations")
async def list_recommendations(user: UserInDB = Depends(get_current_user)):
    run = get_last_run(user.tenant_id)
    if not run:
        return []

    decisions_by_id = {d["proposal_id"]: d for d in run.get("approvals", [])}
    return [
        {**proposal, "policy_decision": decisions_by_id.get(proposal["proposal_id"])}
        for proposal in run.get("proposals", [])
    ]


class RecommendationDecision(BaseModel):
    decision: str  # "approve" | "reject"


@router.post("/recommendations/{proposal_id}/decision")
async def decide_recommendation(proposal_id: str, payload: RecommendationDecision, user: UserInDB = Depends(get_current_user)):
    run = get_last_run(user.tenant_id)
    if not run:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No pipeline run found for this tenant yet.")

    proposal_raw = next((p for p in run.get("proposals", []) if p["proposal_id"] == proposal_id), None)
    if not proposal_raw:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Unknown proposal_id.")

    if payload.decision == "reject":
        return {"proposal_id": proposal_id, "status": "rejected"}
    if payload.decision != "approve":
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "decision must be 'approve' or 'reject'.")

    from apps.api.config import get_settings
    from services.orchestrator.nodes import _executor

    proposal = ActionProposal.model_validate(proposal_raw)
    # A human just overrode the Supervisor's human_review outcome — record
    # that explicitly rather than fabricating an auto_approved decision.
    decision = PolicyDecision(
        proposal_id=proposal.proposal_id,
        outcome="auto_approved",
        risk_score=0.0,
        reason_codes=["HUMAN_APPROVED"],
        reason=f"Manually approved by {user.email} via the Generative UI approval card.",
        policy_version="human-override-v1",
        simulation_allowed=get_settings().execution_enabled,
    )
    record = _executor.execute(proposal=proposal, decision=decision)
    return record.model_dump(mode="json")
