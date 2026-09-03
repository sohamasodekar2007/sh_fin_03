"""POST /v1/chat — the chatbot orchestrator (spec section 5)."""

from __future__ import annotations

from fastapi import APIRouter, Depends

from apps.api.dependencies import get_current_user
from packages.schemas.chat import ChatRequest, ChatResponse
from packages.schemas.schemas import UserInDB
from services.chat.service import handle_chat

router = APIRouter(prefix="/v1", tags=["chat"])


@router.post("/chat", response_model=ChatResponse)
async def chat(payload: ChatRequest, user: UserInDB = Depends(get_current_user)) -> ChatResponse:
    return await handle_chat(payload.messages, user.tenant_id)
