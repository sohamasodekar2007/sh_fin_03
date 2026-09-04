"""
Chatbot Router (Phase 7) — the two-mode chatbot from CHATBOT_ARCHITECTURE.md
on GPT-4o. NOTE: this repo's copy of CHATBOT_ARCHITECTURE.md could not be
found (searched the repo root and docs/) — services/chat/service.py and
services/chat/tools.py were built directly from the Phase 7 prompt's own
detailed spec (tool names, card types, guardrails, test list), which is
self-contained enough to implement against. If the actual document turns
up with different exact shapes, reconcile against it before the frontend
(ChatWidget.tsx, per the build plan) is built against this contract.

Every query is scoped by tenant_id read from the JWT (CurrentUser) — never
from the request body. session_id lookups additionally filter by tenant_id,
so a session_id alone can never surface another tenant's conversation.
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException

from apps.api.db import get_db
from apps.api.dependencies import CurrentUser
from packages.schemas.chat import (
    ChatHistoryResponse,
    ChatMessageRequest,
    ChatMessageResponse,
    ChatSession,
    ChatSessionCreateResponse,
)
from services.chat.service import check_rate_limit, handle_chat_message

router = APIRouter(prefix="/v1/chat", tags=["chat"])


@router.post("/session", response_model=ChatSessionCreateResponse)
async def create_session(current_user: CurrentUser) -> ChatSessionCreateResponse:
    db = get_db()
    session = ChatSession(tenant_id=current_user["tenant_id"], user_id=current_user["user_id"])
    await db.chat_sessions.insert_one(session.model_dump(mode="json"))
    return ChatSessionCreateResponse(session_id=session.session_id)


@router.post("/message", response_model=ChatMessageResponse)
async def send_message(payload: ChatMessageRequest, current_user: CurrentUser) -> ChatMessageResponse:
    db = get_db()
    tenant_id = current_user["tenant_id"]
    user_id = current_user["user_id"]

    if not await check_rate_limit(db, user_id):
        raise HTTPException(status_code=429, detail=f"Rate limit exceeded — max {20} messages/minute.")

    doc = await db.chat_sessions.find_one({"session_id": payload.session_id, "tenant_id": tenant_id})
    if not doc:
        raise HTTPException(status_code=404, detail="Chat session not found")
    doc.pop("_id", None)
    session = ChatSession(**doc)

    try:
        return await handle_chat_message(db, tenant_id, user_id, session, payload)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/history/{session_id}", response_model=ChatHistoryResponse)
async def get_history(session_id: str, current_user: CurrentUser) -> ChatHistoryResponse:
    db = get_db()
    doc = await db.chat_sessions.find_one(
        {"session_id": session_id, "tenant_id": current_user["tenant_id"]}, {"_id": 0}
    )
    if not doc:
        raise HTTPException(status_code=404, detail="Chat session not found")
    session = ChatSession(**doc)
    return ChatHistoryResponse(session_id=session_id, messages=session.messages)
