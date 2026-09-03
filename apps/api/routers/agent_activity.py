"""GET /v1/agent-activity — REST fallback for clients not on the
/ws/agent-feed WebSocket (apps/api/ws/agent_feed.py)."""

from __future__ import annotations

from fastapi import APIRouter, Depends

from apps.api import mock_data
from apps.api.dependencies import get_current_user
from apps.api.pipeline import get_last_run
from packages.schemas.schemas import UserInDB

router = APIRouter(prefix="/v1", tags=["agent-activity"])


@router.get("/agent-activity")
async def agent_activity(user: UserInDB = Depends(get_current_user)):
    run = get_last_run(user.tenant_id)
    if not run:
        return [e.model_dump() for e in mock_data.AGENT_ACTIVITY]

    return [
        {
            "id": f"{event['agent']}-{event['at']}",
            "agent": event["agent"],
            "message": _summarize(event),
            "timestamp": event["at"],
        }
        for event in run.get("trace", [])
    ]


def _summarize(event: dict) -> str:
    agent = event["agent"]
    summary = event.get("summary", {})
    if agent == "Monitor":
        return f"Scanned {summary.get('resources_scanned', 0)} resources across {len(summary.get('providers', {}))} provider(s)"
    if agent == "Analyzer":
        return f"Flagged {summary.get('findings', 0)} finding(s) across {summary.get('resources_evaluated', 0)} resources"
    if agent == "Decision":
        return f"Proposed {summary.get('proposals', 0)} action(s)"
    if agent == "Supervisor":
        outcomes = summary.get("outcomes", {})
        return f"Auto-approved {outcomes.get('auto_approved', 0)}, human review {outcomes.get('human_review', 0)}, blocked {outcomes.get('blocked', 0)}"
    if agent == "Executor":
        return f"Executed {summary.get('executed', 0)} action(s), {summary.get('simulated', 0)} simulated"
    if agent == "Verifier":
        return f"Verified {summary.get('verified', 0)} action(s) — ${summary.get('total_realized_monthly_savings_usd', 0)}/mo realized"
    return str(summary)
