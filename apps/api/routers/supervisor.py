"""
Supervisor Agent Router (Phase 5) — scoring/evidence API plus the
human-approval loop: dashboard buttons (JWT) and the one-click email link
(HMAC-signed, single-use token — the token itself carries the authority to
act, a logged-in session only records WHO clicked it).
"""

from __future__ import annotations

import logging
from typing import Any
from uuid import uuid4

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query, Request
from fastapi.responses import HTMLResponse, JSONResponse
from pydantic import BaseModel

from apps.api.config import get_settings
from apps.api.db import get_db, mongo_available
from apps.api.dependencies import CurrentUser, get_current_user
from apps.api.security import decode_access_token
from services.supervisor.approval_tokens import InvalidApprovalToken, consume_nonce_or_raise, decode_approval_token
from services.supervisor.service import apply_approval_status, run_supervisor_step

router = APIRouter(tags=["supervisor-agent"])
logger = logging.getLogger(__name__)

_STATUS_QUERY_ALIASES = {"pending": "pending_approval"}


class RejectRequest(BaseModel):
    reason: str = ""


def _html_page(ok: bool, message: str) -> str:
    title = "Confirmed" if ok else "Link Unavailable"
    color = "#2F6690" if ok else "#B3261E"
    return f"""<!doctype html><html><head><meta charset="utf-8">
<title>CloudCare — {title}</title>
<style>
body{{font-family:sans-serif;background:#F7FAF9;color:#10222E;display:flex;
align-items:center;justify-content:center;min-height:100vh;margin:0}}
.card{{max-width:420px;background:#fff;border:1px solid #E4EBE8;border-radius:12px;
padding:32px;text-align:center;box-shadow:0 4px 12px rgba(0,0,0,.05)}}
h1{{color:{color};font-size:20px;margin:0 0 12px}}
p{{color:#627785;font-size:14px}}
</style></head>
<body><div class="card"><h1>{title}</h1><p>{message}</p></div></body></html>"""


def _respond(request: Request, ok: bool, action: str | None, proposal_id: str | None, message: str) -> Any:
    accept = request.headers.get("accept", "")
    status_code = 200 if ok else 400
    if "application/json" in accept:
        return JSONResponse(
            {"ok": ok, "action": action, "proposal_id": proposal_id, "message": message}, status_code=status_code
        )
    return HTMLResponse(_html_page(ok, message), status_code=status_code)


def _current_user_id_from_request(request: Request) -> str | None:
    """Best-effort: identifies who clicked, for the audit trail only — the
    signed token is what actually carries authority to act (see module
    docstring). Never raises; a missing/invalid session just means
    confirmed_by stays None."""
    token = request.cookies.get("access_token")
    if not token:
        auth_header = request.headers.get("authorization", "")
        if auth_header.lower().startswith("bearer "):
            token = auth_header[7:]
    if not token:
        return None
    claims = decode_access_token(token)
    return claims.get("sub") if claims else None


async def _execute_after_approval(
    db,
    proposal_doc: dict[str, Any],
    tenant_id: str,
    run_id: str,
) -> dict[str, Any]:
    from services.executor.actions import execute_action

    executable_doc = dict(proposal_doc)
    executable_doc.pop("_id", None)
    executable_doc["tenant_id"] = tenant_id
    executable_doc["status"] = "approved"

    record = await execute_action(db, executable_doc, run_id=run_id)
    update_fields: dict[str, Any] = {
        "execution_id": record.execution_id,
        "execution_status": record.status,
        "execution_mode": record.execution_mode,
        "execution_reason_codes": record.reason_codes,
        "execution_before_state": record.before_state,
        "execution_after_state": record.after_state,
        "execution_rollback_descriptor": record.rollback_descriptor,
        "actual_aws_call_made": record.actual_aws_call_made,
    }
    if record.status in ("executed", "no_op"):
        update_fields["status"] = "executed"

    await db.proposals.update_one(
        {"proposal_id": proposal_doc["proposal_id"], "tenant_id": tenant_id},
        {"$set": update_fields},
    )

    return {
        "execution_id": record.execution_id,
        "execution_status": record.status,
        "execution_mode": record.execution_mode,
        "actual_aws_call_made": record.actual_aws_call_made,
        "reason_codes": record.reason_codes,
    }


# ---------------------------------------------------------------------------
# POST /v1/agent/supervise
# ---------------------------------------------------------------------------


@router.post("/v1/agent/supervise", response_model=dict[str, Any])
async def trigger_supervisor_agent(
    account_id: str | None = Query(default=None),
    region: str | None = Query(default=None),
    run_id: str | None = Query(default=None),
    background_tasks: BackgroundTasks = None,
    current_user: dict = Depends(get_current_user),
) -> dict[str, Any]:
    """Manually (re-)score this tenant's currently-'proposed' proposals and
    send approval emails. The Decision agent already invokes this
    automatically after every /v1/agent/decide run (apps/api/routers/decision.py)
    — this route exists for demos/curl and to re-run scoring on demand."""
    settings = get_settings()
    db = get_db()
    tenant_id = current_user.get("tenant_id", "demo-tenant")
    account_id = account_id or settings.aws_account_id
    region = region or settings.aws_region
    run_id = run_id or str(uuid4())

    docs = await db.proposals.find({"tenant_id": tenant_id, "status": "proposed"}, {"_id": 0}).to_list(length=None)
    if not docs:
        return {
            "status": "success",
            "agent": "Supervisor",
            "run_id": run_id,
            "reviews": [],
            "summary": {"total": 0, "pending_approval": 0, "blocked": 0},
            "message": "No proposed proposals to review — call POST /v1/agent/decide first.",
        }

    result = await run_supervisor_step(
        db, tenant_id, run_id, account_id, region, {"proposals": docs}, background_tasks=background_tasks
    )
    return {
        "status": result["status"],
        "agent": result["agent"],
        "run_id": result["run_id"],
        "reviews": result["reviewed"],
        "summary": result["summary"],
    }


# ---------------------------------------------------------------------------
# GET /v1/approvals — dashboard listing
# ---------------------------------------------------------------------------


@router.get("/v1/approvals", response_model=list[dict[str, Any]])
async def list_approvals(
    current_user: CurrentUser,
    status: str | None = Query(default="pending"),
) -> list[dict[str, Any]]:
    if not await mongo_available():
        if get_settings().app_env != "development":
            raise HTTPException(status_code=503, detail="MongoDB is unavailable")
        return []

    db = get_db()
    tenant_id = current_user["tenant_id"]

    query: dict[str, Any] = {"tenant_id": tenant_id}
    if status:
        query["status"] = _STATUS_QUERY_ALIASES.get(status, status)

    try:
        return await db.proposals.find(query, {"_id": 0}).to_list(length=None)
    except Exception:
        if get_settings().app_env != "development":
            raise
        logger.warning("supervisor: Mongo unavailable; returning development empty approval list", exc_info=True)
        return []


# ---------------------------------------------------------------------------
# POST /v1/approvals/{proposal_id}/approve | /reject — dashboard buttons
# ---------------------------------------------------------------------------


@router.post("/v1/approvals/{proposal_id}/approve", response_model=dict[str, Any])
async def approve_proposal(proposal_id: str, current_user: CurrentUser) -> dict[str, Any]:
    db = get_db()
    tenant_id = current_user["tenant_id"]

    doc = await db.proposals.find_one({"proposal_id": proposal_id, "tenant_id": tenant_id})
    if not doc:
        raise HTTPException(status_code=404, detail="Proposal not found")
    if doc.get("status") != "pending_approval":
        raise HTTPException(status_code=400, detail=f"Proposal is '{doc.get('status')}', not pending approval")

    result = await apply_approval_status(
        db, proposal_id, tenant_id, "approve", current_user["user_id"], via="dashboard"
    )

    result["execution"] = await _execute_after_approval(db, doc, tenant_id, run_id=proposal_id)
    return result


@router.post("/v1/approvals/{proposal_id}/reject", response_model=dict[str, Any])
async def reject_proposal(proposal_id: str, body: RejectRequest, current_user: CurrentUser) -> dict[str, Any]:
    db = get_db()
    tenant_id = current_user["tenant_id"]

    doc = await db.proposals.find_one({"proposal_id": proposal_id, "tenant_id": tenant_id})
    if not doc:
        raise HTTPException(status_code=404, detail="Proposal not found")
    if doc.get("status") != "pending_approval":
        raise HTTPException(status_code=400, detail=f"Proposal is '{doc.get('status')}', not pending approval")

    result = await apply_approval_status(
        db, proposal_id, tenant_id, "reject", current_user["user_id"], via="dashboard", reason=body.reason
    )
    from services.executor.actions import record_rejected_action

    doc = dict(doc)
    doc.pop("_id", None)
    doc["tenant_id"] = tenant_id
    result["execution"] = (
        await record_rejected_action(
            db,
            doc,
            run_id=proposal_id,
            rejected_by=current_user["user_id"],
            reason=body.reason,
        )
    ).model_dump(mode="json")
    return result


# ---------------------------------------------------------------------------
# GET /v1/approvals/email/{token} — the one-click email link
# ---------------------------------------------------------------------------


@router.get("/v1/approvals/email/{token}")
async def confirm_approval_via_email(token: str, request: Request) -> Any:
    db = get_db()
    settings = get_settings()

    try:
        payload = decode_approval_token(token, settings.approval_token_secret)
        await consume_nonce_or_raise(db, payload["nonce"])
    except InvalidApprovalToken as exc:
        return _respond(request, ok=False, action=None, proposal_id=None, message=str(exc))

    proposal_id = payload["proposal_id"]
    tenant_id = payload["tenant_id"]
    action = payload["action"]

    doc = await db.proposals.find_one({"proposal_id": proposal_id, "tenant_id": tenant_id})
    if not doc:
        return _respond(request, ok=False, action=action, proposal_id=proposal_id, message="Proposal not found.")
    if doc.get("status") != "pending_approval":
        return _respond(
            request,
            ok=False,
            action=action,
            proposal_id=proposal_id,
            message=f"Already handled — status is '{doc.get('status')}'.",
        )

    confirmed_by = _current_user_id_from_request(request)
    await apply_approval_status(db, proposal_id, tenant_id, action, confirmed_by, via="email")

    if action == "approve":
        await _execute_after_approval(db, doc, tenant_id, run_id=proposal_id)
    else:
        from services.executor.actions import record_rejected_action

        executable_doc = dict(doc)
        executable_doc.pop("_id", None)
        executable_doc["tenant_id"] = tenant_id
        await record_rejected_action(
            db,
            executable_doc,
            run_id=proposal_id,
            rejected_by=confirmed_by,
            reason="Rejected from approval email",
        )

    verb = "approved" if action == "approve" else "rejected"
    return _respond(request, ok=True, action=action, proposal_id=proposal_id, message=f"Proposal {verb}. You can close this tab.")
