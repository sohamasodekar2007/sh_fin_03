"""
WebSocket /ws/agent-feed — every connected dashboard tab gets each of the
6 LangGraph nodes' trace events the moment apps/api/pipeline.py broadcasts
them, instead of polling GET /v1/agent-activity.
"""

from __future__ import annotations

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from apps.api.ws.manager import manager

router = APIRouter()


@router.websocket("/ws/agent-feed")
async def agent_feed(websocket: WebSocket) -> None:
    await manager.connect(websocket)
    try:
        while True:
            # This feed is broadcast-only; we still need to await something
            # so a client disconnect is detected and cleaned up promptly.
            await websocket.receive_text()
    except WebSocketDisconnect:
        manager.disconnect(websocket)
