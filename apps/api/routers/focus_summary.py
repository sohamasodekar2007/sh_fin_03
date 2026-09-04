"""
Phase 10 — the one new backend surface the frontend dashboard needed: a
real, tenant-scoped FOCUS BilledCost aggregate. Everything else the
dashboard reads already existed (proposals via /v1/approvals,
agent-activity, forecasts).
"""

from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, HTTPException, Query

from apps.api.config import get_settings
from apps.api.db import get_db, mongo_available
from apps.api.dependencies import CurrentUser
from services.focus.dashboard_summary import dashboard_cost_summary

router = APIRouter(prefix="/v1/focus", tags=["focus"])
logger = logging.getLogger(__name__)


@router.get("/cost-summary", response_model=dict[str, Any])
async def cost_summary(current_user: CurrentUser, period_days: int = Query(default=30, ge=1, le=90)) -> dict[str, Any]:
    if not await mongo_available():
        if get_settings().app_env != "development":
            raise HTTPException(status_code=503, detail="MongoDB is unavailable")
        return {
            "period_days": period_days,
            "total_cost_usd": None,
            "prior_total_cost_usd": None,
            "resource_count": 0,
            "message": "No FOCUS data ingested yet for this tenant.",
        }

    db = get_db()
    try:
        return await dashboard_cost_summary(db, current_user["tenant_id"], period_days)
    except Exception:
        if get_settings().app_env != "development":
            raise
        logger.warning("focus_summary: Mongo unavailable; returning development empty summary", exc_info=True)
        return {
            "period_days": period_days,
            "total_cost_usd": None,
            "prior_total_cost_usd": None,
            "resource_count": 0,
            "message": "No FOCUS data ingested yet for this tenant.",
        }
