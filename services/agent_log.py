"""
Per-agent-run activity logging.

Every agent (Monitor, Analyzer, Decision, Supervisor, Executor) wraps its
work with log_agent_run(), writing one document per run to the
`agent_runs` collection — the artifact-per-run the spec requires even when
a run's only output is a JSON payload. apps/api/routers/agent_activity.py
reads from this collection instead of the old AGENT_ACTIVITY mock constant.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal
from uuid import uuid4

from motor.motor_asyncio import AsyncIOMotorDatabase

from apps.api.db import get_db

COLLECTION_NAME = "agent_runs"

AgentName = Literal["Monitor", "Analyzer", "Decision", "Supervisor", "Executor"]
RunStatus = Literal["success", "failed"]


async def ensure_indexes(db: AsyncIOMotorDatabase) -> None:
    await db[COLLECTION_NAME].create_index(
        [("tenant_id", 1), ("run_id", 1), ("started_at", -1)],
        name="tenant_run_started",
    )


async def log_agent_run(
    tenant_id: str,
    run_id: str,
    agent: AgentName,
    status: RunStatus,
    started_at: datetime,
    finished_at: datetime,
    input_summary: dict[str, Any],
    output_summary: dict[str, Any],
    payload: dict[str, Any],
    error: str | None = None,
) -> str:
    """
    Record one agent run. Called once per agent invocation, after the work
    has finished (successfully or not) — `started_at`/`finished_at` bracket
    the whole run so a single document captures both ends of it.
    """
    log_id = str(uuid4())
    duration_ms = int((finished_at - started_at).total_seconds() * 1000)

    doc = {
        "log_id": log_id,
        "tenant_id": tenant_id,
        "run_id": run_id,
        "agent": agent,
        "status": status,
        "started_at": started_at,
        "finished_at": finished_at,
        "duration_ms": duration_ms,
        "input_summary": input_summary,
        "output_summary": output_summary,
        "payload": payload,
        "error": error,
    }

    db = get_db()
    await db[COLLECTION_NAME].insert_one(doc)
    return log_id


async def list_agent_runs(
    tenant_id: str,
    run_id: str | None = None,
    agent: AgentName | None = None,
    limit: int = 100,
) -> list[dict[str, Any]]:
    query: dict[str, Any] = {"tenant_id": tenant_id}
    if run_id:
        query["run_id"] = run_id
    if agent:
        query["agent"] = agent

    db = get_db()
    cursor = db[COLLECTION_NAME].find(query, {"_id": 0}).sort("started_at", -1).limit(limit)
    return await cursor.to_list(length=limit)
