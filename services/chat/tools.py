"""
Tool schemas + implementations for the "existing" mode chatbot (Phase 7).

Every tool is a real function against real collections, scoped by
tenant_id — never from the request body, always from the caller's JWT (see
apps/api/routers/chat.py). No tool here ever mutates anything: approve_proposal
returns an ApprovalCard for the user to click; trigger_monitor_agent
triggers a real scan but never an approval/execution.

Tool descriptions are written as imperative capability statements (not
vague summaries) — a model that gets a vague tool description tends to
answer in prose instead of calling it.
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import Any

from motor.motor_asyncio import AsyncIOMotorDatabase

from apps.api.config import get_settings
from packages.schemas.chat import ApprovalCard
from packages.schemas.focus import FocusDataset

logger = logging.getLogger(__name__)

TOOL_SCHEMAS: list[dict[str, Any]] = [
    {
        "type": "function",
        "function": {
            "name": "get_latest_findings",
            "description": (
                "Get the most recent Analyzer findings (idle resources, over-provisioned "
                "instances, unattached volumes, spend anomalies) detected in this tenant's "
                "connected cloud accounts. Call this whenever the user asks what was found, "
                "what's wasteful, or what issues exist in their cloud account."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "provider": {
                        "type": "string",
                        "enum": ["aws", "azure", "vps"],
                        "description": "Restrict to one cloud provider. Omit to include every connected provider.",
                    }
                },
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_proposal_details",
            "description": (
                "Get full details for one specific cost-optimization proposal by its "
                "proposal_id: the action, expected savings, risk level, confidence score, "
                "and rationale. Call this when the user asks about a specific proposal."
            ),
            "parameters": {
                "type": "object",
                "properties": {"proposal_id": {"type": "string", "description": "The proposal's unique id."}},
                "required": ["proposal_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_cost_summary",
            "description": (
                "Get the tenant's total billed cost and top services by spend over a "
                "trailing window of days. Call this when the user asks about spend, cost "
                "trends, or how much they are paying."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "period_days": {
                        "type": "integer",
                        "minimum": 1,
                        "maximum": 90,
                        "description": "Number of trailing days to summarize.",
                    }
                },
                "required": ["period_days"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "trigger_monitor_agent",
            "description": (
                "Trigger a fresh cloud resource scan (the Monitor agent) for one provider "
                "right now, instead of waiting for the next hourly run. Call this ONLY when "
                "the user explicitly asks to re-scan, refresh, or check right now."
            ),
            "parameters": {
                "type": "object",
                "properties": {"provider": {"type": "string", "enum": ["aws", "azure", "vps"]}},
                "required": ["provider"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "approve_proposal",
            "description": (
                "Prepare an approval card for one specific proposal so the user can review "
                "and click Approve or Reject themselves. This NEVER approves, executes, or "
                "changes anything by itself — it only returns a card for the user's own "
                "action. Call this when the user asks to approve, accept, or act on a "
                "specific proposal."
            ),
            "parameters": {
                "type": "object",
                "properties": {"proposal_id": {"type": "string"}},
                "required": ["proposal_id"],
            },
        },
    },
]

_KNOWN_TOOL_NAMES = {t["function"]["name"] for t in TOOL_SCHEMAS}


class UnknownToolError(Exception):
    pass


# ---------------------------------------------------------------------------
# Tenant-scoped account discovery — analyzer_findings and the Monitor
# trigger key off (account_id, region), not tenant_id directly, so both
# tools below resolve the tenant's own connected accounts first rather
# than trusting an account_id from anywhere else.
# ---------------------------------------------------------------------------


async def _tenant_accounts(db: AsyncIOMotorDatabase, tenant_id: str, provider: str | None = None) -> list[dict[str, Any]]:
    query: dict[str, Any] = {"tenant_id": tenant_id, "connected": True}
    if provider:
        query["provider"] = provider
    accounts = await db.cloud_accounts.find(query, {"_id": 0}).to_list(length=None)
    if accounts:
        return accounts

    # No connected accounts on file — only the single demo tenant this
    # whole build defaults to gets the settings-derived demo accounts
    # (matching services/scheduler.py's own fallback). Any other tenant
    # with no connected accounts genuinely has nothing to show.
    if tenant_id != "demo-tenant":
        return []

    settings = get_settings()
    demo_accounts = [
        {"tenant_id": tenant_id, "provider": "aws", "account_id": settings.aws_account_id or "demo-account", "region": settings.aws_region},
        {"tenant_id": tenant_id, "provider": "azure", "account_id": settings.azure_subscription_id or "demo-subscription", "region": "global"},
    ]
    if settings.vps_host:
        demo_accounts.append({"tenant_id": tenant_id, "provider": "vps", "account_id": settings.vps_host, "region": "on-premises"})
    if provider:
        demo_accounts = [a for a in demo_accounts if a["provider"] == provider]
    return demo_accounts


# ---------------------------------------------------------------------------
# Tool implementations
# ---------------------------------------------------------------------------


async def get_latest_findings(db: AsyncIOMotorDatabase, tenant_id: str, provider: str | None = None) -> dict[str, Any]:
    accounts = await _tenant_accounts(db, tenant_id, provider)
    if not accounts:
        return {"findings": [], "message": "No connected cloud accounts for this tenant."}

    all_findings: list[dict[str, Any]] = []
    for account in accounts:
        doc = await db.analyzer_findings.find_one(
            {"account_id": account["account_id"], "region": account["region"]}, {"_id": 0}
        )
        if doc:
            for finding in doc.get("findings", []):
                all_findings.append({**finding, "provider": account["provider"], "account_id": account["account_id"]})

    return {"findings": all_findings, "count": len(all_findings)}


async def get_proposal_details(db: AsyncIOMotorDatabase, tenant_id: str, proposal_id: str) -> dict[str, Any]:
    doc = await db.proposals.find_one({"proposal_id": proposal_id, "tenant_id": tenant_id}, {"_id": 0})
    if not doc:
        return {"error": f"No proposal {proposal_id!r} found for this tenant."}
    return doc


async def get_cost_summary(db: AsyncIOMotorDatabase, tenant_id: str, period_days: int = 30) -> dict[str, Any]:
    period_days = max(1, min(period_days, 90))
    cutoff = datetime.now(timezone.utc) - timedelta(days=period_days)

    docs = await db.focus_datasets.find({"tenant_id": tenant_id}, {"_id": 0}).to_list(length=None)
    if not docs:
        return {"period_days": period_days, "total_cost_usd": 0.0, "top_services": [], "message": "No FOCUS data ingested yet for this tenant."}

    # Keep only the latest ingestion run per (provider, account_id) so
    # repeated hourly ingests of the same account don't get summed twice.
    latest_by_account: dict[tuple[str, str], dict[str, Any]] = {}
    for doc in docs:
        key = (doc.get("provider", ""), doc.get("account_id", ""))
        existing = latest_by_account.get(key)
        if existing is None or doc.get("ingested_at", "") > existing.get("ingested_at", ""):
            latest_by_account[key] = doc

    total = Decimal("0")
    by_service: dict[str, Decimal] = {}
    for doc in latest_by_account.values():
        dataset = FocusDataset(**doc)
        for record in dataset.records:
            if record.ChargePeriodStart < cutoff:
                continue
            total += record.BilledCost
            by_service[record.ServiceName] = by_service.get(record.ServiceName, Decimal("0")) + record.BilledCost

    top_services = sorted(
        ({"service_name": name, "cost_usd": float(cost)} for name, cost in by_service.items()),
        key=lambda x: x["cost_usd"],
        reverse=True,
    )[:5]

    return {"period_days": period_days, "total_cost_usd": float(total), "top_services": top_services}


async def trigger_monitor_agent(db: AsyncIOMotorDatabase, tenant_id: str, user_id: str, provider: str) -> dict[str, Any]:
    accounts = await _tenant_accounts(db, tenant_id, provider)
    if not accounts:
        return {"error": f"No connected {provider} account for this tenant."}
    account = accounts[0]

    # Lazy import — mirrors services/scheduler.py's own pattern for calling
    # a router function in-process without an HTTP round-trip.
    from apps.api.routers import observation

    fake_user = {"user_id": user_id, "tenant_id": tenant_id, "email": None, "full_name": None}
    result = await observation.trigger_monitor_agent(
        provider=account["provider"],
        account_id=account["account_id"],
        region=account["region"],
        run_id=None,
        current_user=fake_user,
    )
    return {"status": result.get("status"), "resources_found": len(result.get("resources", []) or [])}


async def approve_proposal(db: AsyncIOMotorDatabase, tenant_id: str, proposal_id: str) -> dict[str, Any]:
    """NEVER executes or approves anything — returns an ApprovalCard's
    field data only. The actual approve/reject click goes through
    apps/api/routers/supervisor.py's real, authenticated endpoints."""
    doc = await db.proposals.find_one({"proposal_id": proposal_id, "tenant_id": tenant_id}, {"_id": 0})
    if not doc:
        return {"error": f"No proposal {proposal_id!r} found for this tenant."}

    card = ApprovalCard(
        proposal_id=doc["proposal_id"],
        action=doc.get("action_type", "unknown"),
        target=doc.get("resource_arn", "unknown"),
        savings=float(doc.get("expected_monthly_savings", 0) or 0),
        risk=doc.get("risk_level", "unknown"),
        confidence=float(doc.get("confidence_score") or doc.get("confidence") or 0),
    )
    return {"card": card.model_dump(mode="json"), "status": doc.get("status")}


TOOL_IMPLEMENTATIONS = {
    "get_latest_findings": get_latest_findings,
    "get_proposal_details": get_proposal_details,
    "get_cost_summary": get_cost_summary,
    "trigger_monitor_agent": trigger_monitor_agent,
    "approve_proposal": approve_proposal,
}


async def dispatch_tool(db: AsyncIOMotorDatabase, tenant_id: str, user_id: str, name: str, arguments: dict[str, Any]) -> dict[str, Any]:
    """Every dispatch is tenant-scoped from the caller-provided tenant_id
    (which apps/api/routers/chat.py reads from the JWT, never the request
    body) — no tool implementation above accepts a tenant_id argument from
    the model's tool-call arguments at all, so there is no code path by
    which the model could ask for another tenant's data even if it tried."""
    if name not in _KNOWN_TOOL_NAMES:
        raise UnknownToolError(f"Unknown tool: {name!r}")

    fn = TOOL_IMPLEMENTATIONS[name]
    if name == "trigger_monitor_agent":
        return await fn(db, tenant_id, user_id, **arguments)
    return await fn(db, tenant_id, **arguments)
