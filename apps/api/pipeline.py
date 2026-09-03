"""
Shared entrypoint for running the 6-node LangGraph pipeline (spec section
4) — the one place that invokes build_graph(), caches + persists the
result, and broadcasts each trace event over /ws/agent-feed as it happens.
Every trigger (a REST call from accounts_runs.py, a chat tool call from
services/chat/tools.py, a future cron job) goes through this function so
there's exactly one code path that runs the pipeline.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any
from uuid import uuid4

from apps.api.db import get_db
from apps.api.ws.manager import manager

logger = logging.getLogger(__name__)

# In-process cache of the most recent run per tenant, so the dashboard's
# GET routes (resources/agent-activity/recommendations/savings) have
# something to read synchronously without waiting on Mongo — falls back to
# apps/api/mock_data.py when a tenant has never run the pipeline yet.
_last_run_by_tenant: dict[str, dict[str, Any]] = {}


def get_last_run(tenant_id: str) -> dict[str, Any] | None:
    return _last_run_by_tenant.get(tenant_id)


async def run_pipeline(tenant_id: str, cloud_accounts: list | None = None) -> dict[str, Any]:
    from services.orchestrator.graph import build_graph, make_initial_state

    run_id = str(uuid4())
    graph = build_graph()
    initial_state = make_initial_state(run_id=run_id, tenant_id=tenant_id, account_id="multi-cloud", cloud_accounts=cloud_accounts)

    # graph.invoke() is sync, and nodes.py::monitor() calls asyncio.run()
    # internally per cloud adapter — running it on a worker thread keeps
    # both that asyncio.run() and this route's own event loop valid.
    result: dict[str, Any] = await asyncio.to_thread(graph.invoke, initial_state)

    _last_run_by_tenant[tenant_id] = result

    try:
        db = get_db()
        await db.runs.insert_one({**result, "_id": run_id})
    except Exception as exc:  # noqa: BLE001
        logger.warning("pipeline: failed to persist run %s to Mongo (%s) — in-memory cache only.", run_id, exc)

    for event in result.get("trace", []):
        await manager.broadcast({"type": "agent_trace", **event})

    return result
