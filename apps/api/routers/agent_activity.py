from datetime import datetime, timezone

from fastapi import APIRouter, Depends

from apps.api.dependencies import get_current_user
from packages.schemas.schemas import AgentActivityEntry
from services.agent_log import list_agent_runs

router = APIRouter(prefix="/v1/agent-activity", tags=["agent-activity"])


def _format_timestamp(value: datetime | str) -> str:
    if isinstance(value, str):
        try:
            value = datetime.fromisoformat(value)
        except ValueError:
            return value
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.strftime("%H:%M:%S")


def _to_entry(doc: dict) -> AgentActivityEntry:
    output_summary = doc.get("output_summary") or {}
    message = output_summary.get("message")
    if not message:
        if doc.get("status") == "failed":
            message = f"{doc.get('agent')} run failed: {doc.get('error') or 'unknown error'}"
        else:
            message = f"{doc.get('agent')} run completed"

    return AgentActivityEntry(
        id=doc.get("log_id", ""),
        agent=doc.get("agent", "Monitor"),
        message=message,
        timestamp=_format_timestamp(doc.get("started_at")),
        status=doc.get("status", "success"),
        duration_ms=doc.get("duration_ms", 0),
        payload=doc.get("payload") or {},
    )


@router.get("", response_model=list[AgentActivityEntry])
async def list_agent_activity(
    run_id: str | None = None,
    agent: str | None = None,
    limit: int = 100,
    current_user: dict = Depends(get_current_user),
) -> list[AgentActivityEntry]:
    """Reads the real per-run audit trail from the `agent_runs` collection
    (services/agent_log.py) — every Monitor/Analyzer/Decision/Supervisor/
    Executor invocation logs one document there, tenant-scoped."""
    docs = await list_agent_runs(
        tenant_id=current_user["tenant_id"],
        run_id=run_id,
        agent=agent,  # type: ignore[arg-type]
        limit=limit,
    )
    return [_to_entry(doc) for doc in docs]
