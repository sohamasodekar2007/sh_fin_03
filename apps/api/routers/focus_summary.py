"""
Phase 10 — the one new backend surface the frontend dashboard needed: a
real, tenant-scoped FOCUS BilledCost aggregate. Everything else the
dashboard reads already existed (proposals via /v1/approvals,
agent-activity, forecasts).
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Query

from apps.api.db import get_db
from apps.api.dependencies import CurrentUser
from services.focus.dashboard_summary import dashboard_cost_summary

router = APIRouter(prefix="/v1/focus", tags=["focus"])


@router.get("/cost-summary", response_model=dict[str, Any])
async def cost_summary(current_user: CurrentUser, period_days: int = Query(default=30, ge=1, le=90)) -> dict[str, Any]:
    db = get_db()
    return await dashboard_cost_summary(db, current_user["tenant_id"], period_days)
