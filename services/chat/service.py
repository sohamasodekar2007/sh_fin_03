"""
Chat orchestrator (spec section 5). POST /v1/chat -> here.

With OPENAI_API_KEY set: a real OpenAI function-calling loop over
TOOL_SCHEMAS (services/chat/tools.py) — the model picks a tool, we execute
the real backend function, feed the result back, and let the model write
the final reply. Every tool call that surfaces a REQUIRE_HUMAN proposal
gets an ApprovalCardPayload attached so the Next.js chat window can render
the Generative UI approval card inline instead of describing it in prose.

Without a key: a small deterministic keyword router over the same tool
functions, so the chat endpoint still does real work (trigger a scan, list
findings, list pending approvals) rather than going dark.
"""

from __future__ import annotations

import inspect
import json
import logging

from apps.api.config import get_settings
from packages.schemas.chat import ApprovalCardPayload, ChatMessage, ChatResponse
from services.chat.tools import TOOL_IMPLEMENTATIONS, TOOL_SCHEMAS

logger = logging.getLogger(__name__)


async def _call_tool(name: str, tenant_id: str) -> dict:
    fn = TOOL_IMPLEMENTATIONS.get(name)
    if not fn:
        return {"error": f"Unknown tool: {name}"}
    result = fn(tenant_id) if not inspect.iscoroutinefunction(fn) else await fn(tenant_id)
    return result


def _approval_card_from(tool_name: str, tool_result: dict) -> ApprovalCardPayload | None:
    if tool_name != "list_pending_approvals":
        return None
    pending = tool_result.get("pending", [])
    if not pending:
        return None
    proposal = pending[0]
    return ApprovalCardPayload(
        proposal_id=proposal["proposal_id"],
        resource_id=proposal["resource_id"],
        action_template=proposal["action_template"],
        rationale=proposal["rationale"],
        estimated_monthly_savings_usd=float(proposal["estimated_monthly_savings_usd"]),
        risk_score=0.5,
        risk_reason="Routed to human review by the Supervisor Agent — see /v1/recommendations for the full policy decision.",
    )


async def _deterministic_reply(user_text: str, tenant_id: str) -> ChatResponse:
    """No OPENAI_API_KEY — keyword-routed fallback so /v1/chat still does
    real work instead of going dark."""
    text = user_text.lower()

    if any(k in text for k in ("scan", "refresh", "check my cloud", "run monitor")):
        result = await _call_tool("trigger_monitor_agent", tenant_id)
        return ChatResponse(content=f"Ran a full scan: {result['resources_scanned']} resources scanned, {result['findings']} finding(s), {result['proposals']} action(s) proposed, {result['executed']} auto-executed.")

    if any(k in text for k in ("approve", "pending", "review", "waiting")):
        result = await _call_tool("list_pending_approvals", tenant_id)
        card = _approval_card_from("list_pending_approvals", result)
        pending = result.get("pending", [])
        if not pending:
            return ChatResponse(content="Nothing is waiting on your approval right now.")
        return ChatResponse(content=f"{len(pending)} action(s) need your approval. Here's the highest-priority one:", ui=card)

    if any(k in text for k in ("wasted", "idle", "finding", "anomal")):
        result = await _call_tool("run_analyzer_agent", tenant_id)
        if "message" in result:
            return ChatResponse(content=result["message"])
        lines = "\n".join(f"- {f['resource_id']}: {f['rule_id']} (confidence {f['confidence']:.2f})" for f in result["findings"])
        return ChatResponse(content=f"{result['finding_count']} finding(s) from the last scan:\n{lines}")

    if any(k in text for k in ("cost", "spend", "saving", "money")):
        result = await _call_tool("get_savings_summary", tenant_id)
        if "message" in result:
            return ChatResponse(content=result["message"])
        return ChatResponse(content=f"Total monthly spend: ${result['total_monthly_spend_usd']:,.2f}. Savings realized this month: ${result['savings_this_month_usd']:,.2f}, across {result['resources_monitored']} resources.")

    return ChatResponse(
        content=(
            "I can run a scan, list wasted resources, summarize spend, or show what's pending your approval. "
            "(No OPENAI_API_KEY is configured, so I'm keyword-matching rather than reasoning freely — try "
            "\"scan my cloud\", \"show wasted resources\", \"what needs my approval\", or \"what's my spend\".)"
        )
    )


async def handle_chat(messages: list[ChatMessage], tenant_id: str) -> ChatResponse:
    settings = get_settings()
    user_text = messages[-1].content if messages else ""

    if not settings.openai_api_key:
        return await _deterministic_reply(user_text, tenant_id)

    try:
        from openai import OpenAI

        client = OpenAI(api_key=settings.openai_api_key)
        openai_messages = [
            {
                "role": "system",
                "content": (
                    "You are CloudCare's FinOps assistant. You can only act through the provided tools — "
                    "never claim to have scanned, found, or saved anything unless a tool call actually "
                    "returned that result. Be concise."
                ),
            },
            *[{"role": m.role, "content": m.content} for m in messages],
        ]

        response = client.chat.completions.create(
            model=settings.openai_model,
            messages=openai_messages,
            tools=TOOL_SCHEMAS,
            temperature=0.3,
        )
        message = response.choices[0].message

        if not message.tool_calls:
            return ChatResponse(content=message.content or "")

        tool_call = message.tool_calls[0]
        tool_result = await _call_tool(tool_call.function.name, tenant_id)

        follow_up = client.chat.completions.create(
            model=settings.openai_model,
            messages=[
                *openai_messages,
                {"role": "assistant", "content": None, "tool_calls": [tool_call.model_dump()]},
                {"role": "tool", "tool_call_id": tool_call.id, "content": json.dumps(tool_result, default=str)},
            ],
            temperature=0.3,
        )
        final_text = follow_up.choices[0].message.content or ""
        ui = _approval_card_from(tool_call.function.name, tool_result)
        return ChatResponse(content=final_text, ui=ui, tool_called=tool_call.function.name)

    except Exception as exc:  # noqa: BLE001
        logger.warning("chat.service: OpenAI call failed (%s) — falling back to keyword router.", exc)
        return await _deterministic_reply(user_text, tenant_id)
