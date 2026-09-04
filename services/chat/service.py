"""
Chatbot orchestrator (Phase 7) — two modes over the SAME GPT-4o client
built in Phase 4 (services/llm/client.py). No second LLM client.

This repo's copy of CHATBOT_ARCHITECTURE.md was not found (see
apps/api/routers/chat.py's module docstring) — the tool set, card types,
and guardrails below are built directly from the Phase 7 prompt's own
explicit spec, which is self-contained enough to implement against.

MODE "existing": tool-calling loop (services/chat/tools.py) over a system
message that embeds the tenant's actual latest proposals as a structured
JSON block — never prose — so the model cites real numbers instead of
inventing them. Capped at MAX_TOOL_ROUNDS to avoid an infinite tool loop;
on a cap-out, returns the best-effort answer rather than erroring.

MODE "new": one structured-JSON call (LLMClient.complete(), the same
method the Decision agent uses) against a Pydantic-validated intake form.

GUARDRAILS:
  - The chatbot never executes anything. approve_proposal only ever
    returns an ApprovalCard; the real approve/reject click goes through
    apps/api/routers/supervisor.py with real auth.
  - Every query is scoped by tenant_id passed in from the caller (which
    apps/api/routers/chat.py reads from the JWT) — no tool implementation
    accepts a tenant_id from the model's own arguments.
  - History capped at 20 stored messages; rate-limited to 20 messages per
    user per minute (see check_rate_limit).
  - On LLMUnavailable (no API key, or every retry exhausted), both modes
    degrade to a deterministic, clearly-labeled fallback built from real
    data already fetched — never silent, never fabricated numbers.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timedelta, timezone
from typing import Any

from motor.motor_asyncio import AsyncIOMotorDatabase
from pydantic import ValidationError

from packages.schemas.chat import (
    ApprovalCard,
    ChatCard,
    ChatMessage,
    ChatMessageRequest,
    ChatMessageResponse,
    ChatSession,
    CostSummaryCard,
    FindingCard,
    NewWorkloadForm,
    RecommendationCard,
    RecommendationOption,
)
from services.chat.tools import TOOL_SCHEMAS, UnknownToolError, dispatch_tool
from services.llm.client import LLMClient, LLMUnavailable

logger = logging.getLogger(__name__)

MAX_TOOL_ROUNDS = 5
MAX_HISTORY_MESSAGES = 20  # a "turn" is one message; ~10 user/assistant exchanges
MAX_MESSAGES_PER_MINUTE = 20

_SYSTEM_PROMPT_EXISTING = (
    "You are CloudCare's assistant for an already-connected cloud account. You have "
    "tools to fetch real findings, proposal details, cost summaries, trigger a fresh "
    "scan, and prepare an approval card. NEVER invent a resource id, dollar figure, "
    "or proposal id — only state numbers that came from a tool result or the CONTEXT "
    "block below, and cite them verbatim. If the data you need isn't in CONTEXT, call "
    "a tool to get it rather than guessing. You can NEVER execute, approve, or reject "
    "anything yourself — approve_proposal only ever prepares a card for the user to "
    "click; you never take the action described in it.\n\n"
    "CONTEXT (this tenant's latest Decision agent proposals, with Supervisor scores):\n{context}"
)

_NEW_MODE_SYSTEM_PROMPT = (
    "You are CloudCare's cloud architecture advisor for a NEW workload that has not "
    "been deployed yet. Given the intake form, recommend a cloud approach. Give "
    "2-3 concrete, named options with a realistic estimated_monthly_cost_usd for EACH "
    "(never below realistic list pricing for the stated budget and scale), pros and "
    "cons for each, a one-paragraph reasoning, and an overall summary recommendation. "
    "Respond with JSON only, matching the given schema exactly."
)

_NEW_MODE_JSON_SCHEMA = {
    "name": "recommendation",
    "schema": {
        "type": "object",
        "properties": {
            "summary": {"type": "string"},
            "estimated_monthly_cost_usd": {"type": "number"},
            "reasoning": {"type": "string"},
            "options": {
                "type": "array",
                "minItems": 2,
                "maxItems": 3,
                "items": {
                    "type": "object",
                    "properties": {
                        "name": {"type": "string"},
                        "estimated_monthly_cost_usd": {"type": "number"},
                        "pros": {"type": "array", "items": {"type": "string"}},
                        "cons": {"type": "array", "items": {"type": "string"}},
                    },
                    "required": ["name", "estimated_monthly_cost_usd", "pros", "cons"],
                    "additionalProperties": False,
                },
            },
        },
        "required": ["summary", "estimated_monthly_cost_usd", "reasoning", "options"],
        "additionalProperties": False,
    },
    "strict": True,
}


# ---------------------------------------------------------------------------
# Indexes / persistence / rate limiting
# ---------------------------------------------------------------------------


async def ensure_chat_indexes(db: AsyncIOMotorDatabase) -> None:
    await db.chat_sessions.create_index("session_id", unique=True, name="session_id_unique")
    await db.chat_sessions.create_index([("tenant_id", 1)], name="tenant_id")
    await db.chat_rate_limits.create_index("key", unique=True, name="key_unique")
    await db.chat_rate_limits.create_index("expires_at", expireAfterSeconds=0, name="rate_limit_ttl")


async def check_rate_limit(db: AsyncIOMotorDatabase, user_id: str) -> bool:
    """True if allowed. Atomic per-minute counter (findOneAndUpdate $inc),
    keyed on (user_id, minute-bucket) — no Redis needed."""
    from pymongo import ReturnDocument

    bucket = datetime.now(timezone.utc).strftime("%Y%m%d%H%M")
    key = f"{user_id}:{bucket}"
    doc = await db.chat_rate_limits.find_one_and_update(
        {"key": key},
        {"$inc": {"count": 1}, "$setOnInsert": {"expires_at": datetime.now(timezone.utc) + timedelta(minutes=2)}},
        upsert=True,
        return_document=ReturnDocument.AFTER,
    )
    return doc["count"] <= MAX_MESSAGES_PER_MINUTE


async def _save_session(db: AsyncIOMotorDatabase, session: ChatSession) -> None:
    session.updated_at = datetime.now(timezone.utc)
    await db.chat_sessions.update_one(
        {"session_id": session.session_id}, {"$set": session.model_dump(mode="json")}, upsert=True
    )


def _trim_history(session: ChatSession) -> None:
    if len(session.messages) > MAX_HISTORY_MESSAGES:
        session.messages = session.messages[-MAX_HISTORY_MESSAGES:]


# ---------------------------------------------------------------------------
# Mode "existing" — tool-calling loop
# ---------------------------------------------------------------------------


async def _build_existing_mode_context(db: AsyncIOMotorDatabase, tenant_id: str) -> str:
    proposals = await db.proposals.find({"tenant_id": tenant_id}, {"_id": 0}).sort("confidence_score", -1).limit(10).to_list(length=10)
    return json.dumps({"latest_proposals": proposals}, default=str)


def _cards_from_tool_result(name: str, result: dict[str, Any]) -> list[ChatCard]:
    if "error" in result:
        return []

    if name == "approve_proposal" and "card" in result:
        try:
            return [ApprovalCard(**result["card"])]
        except ValidationError:
            return []

    if name == "get_cost_summary" and "total_cost_usd" in result:
        try:
            return [
                CostSummaryCard(
                    period_days=result["period_days"],
                    total_cost_usd=result["total_cost_usd"],
                    top_services=result.get("top_services", []),
                )
            ]
        except ValidationError:
            return []

    if name == "get_latest_findings":
        cards: list[ChatCard] = []
        for f in (result.get("findings") or [])[:5]:
            try:
                cards.append(
                    FindingCard(
                        resource_id=f.get("resource_id", "unknown"),
                        rule_id=f.get("rule_id", "unknown"),
                        summary=f.get("rationale") or f"{f.get('rule_id', 'finding')} on {f.get('resource_id', 'unknown')}",
                        evidence=f.get("evidence") if isinstance(f.get("evidence"), dict) else {},
                    )
                )
            except ValidationError:
                continue
        return cards

    return []


def _deterministic_existing_mode_fallback(context_json: str) -> str:
    try:
        context = json.loads(context_json)
    except (json.JSONDecodeError, TypeError):
        return "The AI model is currently unavailable, and I don't have any cached findings to share right now."

    proposals = context.get("latest_proposals", [])
    if not proposals:
        return "The AI model is currently unavailable, and there are no proposals on file yet for this account."

    lines = ["The AI model is currently unavailable — here's what's on file, unfiltered:"]
    for p in proposals[:5]:
        lines.append(
            f"- {p.get('action_type', 'unknown action')} on {p.get('resource_arn', 'unknown resource')}: "
            f"~${p.get('expected_monthly_savings', '0')}/mo, risk={p.get('risk_level', 'unknown')}"
        )
    return "\n".join(lines)


def _outbound_tool_call_message(content: str | None, tool_calls: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "role": "assistant",
        "content": content,
        "tool_calls": [
            {"id": tc["id"], "type": "function", "function": {"name": tc["name"], "arguments": json.dumps(tc["arguments"])}}
            for tc in tool_calls
        ],
    }


async def _run_existing_mode(
    db: AsyncIOMotorDatabase, tenant_id: str, user_id: str, session: ChatSession, user_content: str
) -> ChatMessageResponse:
    client = LLMClient()

    context_json = await _build_existing_mode_context(db, tenant_id)
    system_content = _SYSTEM_PROMPT_EXISTING.format(context=context_json)

    session.messages.append(ChatMessage(role="user", content=user_content))
    _trim_history(session)

    outbound_messages: list[dict[str, Any]] = [{"role": "system", "content": system_content}]
    outbound_messages.extend({"role": m.role, "content": m.content} for m in session.messages)

    tool_calls_made: list[str] = []
    cards: list[ChatCard] = []
    final_content: str | None = None

    try:
        for _round in range(MAX_TOOL_ROUNDS):
            result = await client.complete_with_tools(outbound_messages, TOOL_SCHEMAS, tool_choice="auto")
            tool_calls = result["tool_calls"]

            if not tool_calls:
                final_content = result["content"] or "I don't have anything more to add."
                break

            outbound_messages.append(_outbound_tool_call_message(result["content"], tool_calls))

            for tc in tool_calls:
                try:
                    tool_result = await dispatch_tool(db, tenant_id, user_id, tc["name"], tc["arguments"])
                except UnknownToolError as exc:
                    tool_result = {"error": str(exc)}
                except Exception as exc:  # noqa: BLE001 - a broken tool must not crash the chat turn
                    logger.exception("chat: tool %s failed", tc["name"])
                    tool_result = {"error": f"Tool failed: {exc}"}

                tool_calls_made.append(tc["name"])
                cards.extend(_cards_from_tool_result(tc["name"], tool_result))
                outbound_messages.append({"role": "tool", "tool_call_id": tc["id"], "content": json.dumps(tool_result, default=str)})
        else:
            final_content = "I gathered some information but couldn't finish reasoning about it in time — here's what I found so far."
    except LLMUnavailable:
        final_content = _deterministic_existing_mode_fallback(context_json)

    assistant_message = ChatMessage(role="assistant", content=final_content or "")
    session.messages.append(assistant_message)
    _trim_history(session)
    await _save_session(db, session)

    return ChatMessageResponse(
        session_id=session.session_id, content=final_content or "", cards=cards, tool_calls_made=tool_calls_made
    )


# ---------------------------------------------------------------------------
# Mode "new" — one structured-JSON recommendation
# ---------------------------------------------------------------------------


def _deterministic_recommendation(form: NewWorkloadForm) -> RecommendationCard:
    budget = form.monthly_budget
    options = [
        RecommendationOption(
            name="Pay-as-you-go (on-demand)",
            estimated_monthly_cost_usd=round(budget * 0.6, 2),
            pros=["No upfront commitment", "Scales elastically with usage"],
            cons=["Costs can spike unpredictably"],
        ),
        RecommendationOption(
            name="Reserved capacity / savings plan",
            estimated_monthly_cost_usd=round(budget * 0.45, 2),
            pros=["Lower steady-state cost"],
            cons=["Requires a 1-3 year commitment"],
        ),
    ]
    return RecommendationCard(
        summary=(
            f"Based on a {form.company_size.replace('_', ' ')} workload with a "
            f"${budget:,.0f}/mo budget, start pay-as-you-go and move to reserved "
            f"capacity once usage patterns stabilize."
        ),
        estimated_monthly_cost_usd=options[0].estimated_monthly_cost_usd,
        reasoning="The AI model is currently unavailable, so this is a conservative rule-of-thumb estimate, not a live recommendation.",
        options=options,
    )


async def _run_new_mode(
    db: AsyncIOMotorDatabase,
    tenant_id: str,
    user_id: str,
    session: ChatSession,
    form: NewWorkloadForm,
    user_content: str,
) -> ChatMessageResponse:
    client = LLMClient()
    user_payload = json.dumps({"intake_form": form.model_dump(), "user_message": user_content})

    try:
        raw = await client.complete(system=_NEW_MODE_SYSTEM_PROMPT, user=user_payload, json_schema=_NEW_MODE_JSON_SCHEMA)
        card = RecommendationCard(**raw)
    except (LLMUnavailable, ValidationError, ValueError, TypeError, KeyError) as exc:
        logger.warning("chat: new-mode recommendation failed, using deterministic fallback: %s", exc)
        card = _deterministic_recommendation(form)

    session.messages.append(ChatMessage(role="user", content=user_content))
    session.messages.append(ChatMessage(role="assistant", content=card.summary))
    _trim_history(session)
    await _save_session(db, session)

    return ChatMessageResponse(session_id=session.session_id, content=card.summary, cards=[card], tool_calls_made=[])


# ---------------------------------------------------------------------------
# Entrypoint
# ---------------------------------------------------------------------------


async def handle_chat_message(
    db: AsyncIOMotorDatabase, tenant_id: str, user_id: str, session: ChatSession, req: ChatMessageRequest
) -> ChatMessageResponse:
    if req.mode == "new":
        if req.form_data is None:
            raise ValueError("mode='new' requires form_data")
        return await _run_new_mode(db, tenant_id, user_id, session, req.form_data, req.content)
    return await _run_existing_mode(db, tenant_id, user_id, session, req.content)
