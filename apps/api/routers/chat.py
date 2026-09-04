"""
Chatbot Router (Phase 7).

Every query is scoped by tenant_id read from the JWT (CurrentUser), never
from the request body. session_id lookups additionally filter by tenant_id,
so a session_id alone can never surface another tenant's conversation.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException

from apps.api.config import get_settings
from apps.api.db import get_db, mongo_available
from apps.api.dependencies import CurrentUser
from packages.schemas.chat import (
    ChatHistoryResponse,
    ChatMessage,
    ChatMessageRequest,
    ChatMessageResponse,
    ChatSession,
    ChatSessionCreateResponse,
)
from services.chat.service import check_rate_limit, handle_chat_message

router = APIRouter(prefix="/v1/chat", tags=["chat"])
logger = logging.getLogger(__name__)
_DEV_CHAT_SESSIONS: dict[str, ChatSession] = {}


def _dev_chat_enabled() -> bool:
    return get_settings().app_env == "development"


def _store_dev_session(session: ChatSession) -> None:
    session.updated_at = datetime.now(timezone.utc)
    _DEV_CHAT_SESSIONS[session.session_id] = session


def _development_unavailable_response(session: ChatSession, payload: ChatMessageRequest) -> ChatMessageResponse:
    session.messages.append(ChatMessage(role="user", content=payload.content))
    content = (
        "CloudCareAI is running in development mode, but MongoDB is unavailable. "
        "I can keep this chat open, but spend, findings, approvals, and scan tools need MongoDB data before I can ground an answer."
    )
    session.messages.append(ChatMessage(role="assistant", content=content))
    _store_dev_session(session)
    return ChatMessageResponse(session_id=session.session_id, content=content, cards=[], tool_calls_made=[])


@router.post("/session", response_model=ChatSessionCreateResponse)
async def create_session(current_user: CurrentUser) -> ChatSessionCreateResponse:
    session = ChatSession(tenant_id=current_user["tenant_id"], user_id=current_user["user_id"])
    if not await mongo_available():
        if not _dev_chat_enabled():
            raise HTTPException(status_code=503, detail="MongoDB is unavailable")
        _store_dev_session(session)
        return ChatSessionCreateResponse(session_id=session.session_id)

    db = get_db()
    try:
        await db.chat_sessions.insert_one(session.model_dump(mode="json"))
    except Exception:
        if not _dev_chat_enabled():
            raise
        logger.warning("chat: Mongo unavailable; creating development in-memory session", exc_info=True)
        _store_dev_session(session)
    return ChatSessionCreateResponse(session_id=session.session_id)


@router.post("/message", response_model=ChatMessageResponse)
async def send_message(payload: ChatMessageRequest, current_user: CurrentUser) -> ChatMessageResponse:
    tenant_id = current_user["tenant_id"]
    user_id = current_user["user_id"]

    if not await mongo_available():
        if not _dev_chat_enabled():
            raise HTTPException(status_code=503, detail="MongoDB is unavailable")
        session = _DEV_CHAT_SESSIONS.get(payload.session_id)
        if not session or session.tenant_id != tenant_id:
            raise HTTPException(status_code=404, detail="Chat session not found")
        return _development_unavailable_response(session, payload)

    db = get_db()
    try:
        if not await check_rate_limit(db, user_id):
            raise HTTPException(status_code=429, detail="Rate limit exceeded - max 20 messages/minute.")

        doc = await db.chat_sessions.find_one({"session_id": payload.session_id, "tenant_id": tenant_id})
        if not doc:
            raise HTTPException(status_code=404, detail="Chat session not found")
        doc.pop("_id", None)
        session = ChatSession(**doc)
    except HTTPException:
        raise
    except Exception:
        if not _dev_chat_enabled():
            raise
        logger.warning("chat: Mongo unavailable; answering from development in-memory session", exc_info=True)
        session = _DEV_CHAT_SESSIONS.get(payload.session_id)
        if not session or session.tenant_id != tenant_id:
            raise HTTPException(status_code=404, detail="Chat session not found")
        return _development_unavailable_response(session, payload)

    try:
        return await handle_chat_message(db, tenant_id, user_id, session, payload)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception:
        if not _dev_chat_enabled():
            raise
        logger.warning("chat: Mongo-backed turn failed; answering from development in-memory session", exc_info=True)
        _store_dev_session(session)
        return _development_unavailable_response(session, payload)


@router.get("/history/{session_id}", response_model=ChatHistoryResponse)
async def get_history(session_id: str, current_user: CurrentUser) -> ChatHistoryResponse:
    if not await mongo_available():
        if _dev_chat_enabled():
            session = _DEV_CHAT_SESSIONS.get(session_id)
            if session and session.tenant_id == current_user["tenant_id"]:
                return ChatHistoryResponse(session_id=session_id, messages=session.messages)
        raise HTTPException(status_code=404, detail="Chat session not found")

    db = get_db()
    try:
        doc = await db.chat_sessions.find_one(
            {"session_id": session_id, "tenant_id": current_user["tenant_id"]}, {"_id": 0}
        )
    except Exception:
        if _dev_chat_enabled():
            session = _DEV_CHAT_SESSIONS.get(session_id)
            if session and session.tenant_id == current_user["tenant_id"]:
                return ChatHistoryResponse(session_id=session_id, messages=session.messages)
        raise
    if not doc:
        raise HTTPException(status_code=404, detail="Chat session not found")
    session = ChatSession(**doc)
    return ChatHistoryResponse(session_id=session_id, messages=session.messages)
