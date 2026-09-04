from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient

from apps.api.dependencies import get_current_user
from apps.api.main import app
from packages.schemas.chat import ApprovalCard, ChatMessageRequest, ChatSession, CostSummaryCard
from services.chat.service import handle_chat_message
from services.chat.tools import UnknownToolError, dispatch_tool
from services.llm.client import LLMUnavailable


# ---------------------------------------------------------------------------
# Minimal in-memory fake of the Motor collection/db interface.
# ---------------------------------------------------------------------------


class _FakeCursor:
    def __init__(self, docs):
        self._docs = docs

    def sort(self, *_a, **_kw):
        return self

    def limit(self, n):
        self._docs = self._docs[:n]
        return self

    async def to_list(self, length=None):
        return list(self._docs)


class _FakeCollection:
    def __init__(self):
        self.docs: list[dict] = []
        self.update_calls: list[tuple] = []

    def seed(self, *docs):
        self.docs.extend(dict(d) for d in docs)

    async def insert_one(self, doc):
        self.docs.append(dict(doc))

    async def find_one(self, query, *_a, **_kw):
        for doc in self.docs:
            if all(doc.get(k) == v for k, v in query.items()):
                return dict(doc)
        return None

    async def find_one_and_update(self, query, update, upsert=False, return_document=None):
        existing = None
        for doc in self.docs:
            if all(doc.get(k) == v for k, v in query.items()):
                existing = doc
                break
        if existing is None:
            if not upsert:
                return None
            existing = dict(query)
            self.docs.append(existing)
        existing["count"] = existing.get("count", 0) + update.get("$inc", {}).get("count", 0)
        for k, v in update.get("$setOnInsert", {}).items():
            existing.setdefault(k, v)
        return dict(existing)

    async def update_one(self, query, update, upsert=False):
        self.update_calls.append((query, update))
        for doc in self.docs:
            if all(doc.get(k) == v for k, v in query.items()):
                doc.update(update.get("$set", {}))
                return
        if upsert:
            new_doc = dict(query)
            new_doc.update(update.get("$set", {}))
            self.docs.append(new_doc)

    def find(self, query=None, *_a, **_kw):
        query = query or {}
        return _FakeCursor([d for d in self.docs if all(d.get(k) == v for k, v in query.items())])

    async def create_index(self, *a, **kw):
        pass


class _FakeDB:
    def __init__(self):
        self._collections: dict[str, _FakeCollection] = {}

    def _get(self, name):
        return self._collections.setdefault(name, _FakeCollection())

    def __getitem__(self, name):
        return self._get(name)

    def __getattr__(self, name):
        return self._get(name)


def _proposal(tenant_id="tenant-a", proposal_id="p1", status="pending_approval"):
    return {
        "proposal_id": proposal_id,
        "tenant_id": tenant_id,
        "resource_arn": "arn:aws:ec2:ap-south-1:demo:instance/i-1",
        "action_type": "stop_instance",
        "template_id": "ec2.stop.v1",
        "parameters": {"instance_id": "i-1", "region": "ap-south-1"},
        "expected_monthly_savings": "42.00",
        "risk_level": "low",
        "confidence": 0.8,
        "confidence_score": 0.8,
        "status": status,
    }


def _session(tenant_id="tenant-a", session_id="s1"):
    return ChatSession(session_id=session_id, tenant_id=tenant_id, user_id="u1")


# ---------------------------------------------------------------------------
# (a) Tool call parsed and dispatched
# ---------------------------------------------------------------------------


def test_dispatch_tool_calls_get_proposal_details():
    db = _FakeDB()
    db.proposals.seed(_proposal())

    result = asyncio.run(dispatch_tool(db, "tenant-a", "u1", "get_proposal_details", {"proposal_id": "p1"}))

    assert result["proposal_id"] == "p1"
    assert result["action_type"] == "stop_instance"


def test_existing_mode_dispatches_tool_call_from_llm_response():
    db = _FakeDB()
    db.proposals.seed(_proposal())

    mock_client = AsyncMock()
    mock_client.complete_with_tools.side_effect = [
        {"content": None, "tool_calls": [{"id": "call_1", "name": "get_cost_summary", "arguments": {"period_days": 30}}]},
        {"content": "You've spent $0 in the last 30 days (no FOCUS data on file yet).", "tool_calls": []},
    ]

    with patch("services.chat.service.LLMClient", return_value=mock_client):
        response = asyncio.run(handle_chat_message(
            db, "tenant-a", "u1", _session(),
            ChatMessageRequest(session_id="s1", mode="existing", content="How much have I spent?"),
        ))

    assert "tool_calls_made" not in ("",)  # sanity — response object below is the real assertion
    assert response.tool_calls_made == ["get_cost_summary"]
    assert mock_client.complete_with_tools.await_count == 2
    assert any(isinstance(c, CostSummaryCard) for c in response.cards)


# ---------------------------------------------------------------------------
# (b) Unknown tool name rejected
# ---------------------------------------------------------------------------


def test_dispatch_tool_rejects_unknown_tool_name():
    db = _FakeDB()
    with pytest.raises(UnknownToolError):
        asyncio.run(dispatch_tool(db, "tenant-a", "u1", "delete_everything", {}))


# ---------------------------------------------------------------------------
# (c) Cross-tenant data never returned
# ---------------------------------------------------------------------------


def test_get_proposal_details_is_tenant_scoped():
    db = _FakeDB()
    db.proposals.seed(
        _proposal(tenant_id="tenant-a", proposal_id="p1"),
        _proposal(tenant_id="tenant-b", proposal_id="p1"),
    )
    db.proposals.docs[1]["resource_arn"] = "arn:aws:ec2:ap-south-1:demo:instance/SECRET-tenant-b-instance"

    result = asyncio.run(dispatch_tool(db, "tenant-a", "u1", "get_proposal_details", {"proposal_id": "p1"}))

    assert result["tenant_id"] == "tenant-a"
    assert "SECRET" not in result["resource_arn"]


def test_chat_message_endpoint_never_leaks_another_tenants_session():
    db = _FakeDB()
    session_doc = _session(tenant_id="tenant-a", session_id="shared-session-id").model_dump(mode="json")
    db.chat_sessions.seed(session_doc)

    app.dependency_overrides[get_current_user] = lambda: {
        "user_id": "attacker", "tenant_id": "tenant-b", "email": None, "full_name": None,
    }
    try:
        with patch("apps.api.routers.chat.get_db", return_value=db):
            client = TestClient(app)
            res = client.post(
                "/v1/chat/message",
                json={"session_id": "shared-session-id", "mode": "existing", "content": "show me everything"},
            )
    finally:
        app.dependency_overrides.clear()

    # tenant-b's JWT, tenant-a's session_id — must 404, never serve tenant-a's session.
    assert res.status_code == 404


# ---------------------------------------------------------------------------
# (d) approve_proposal returns a card rather than mutating anything
# ---------------------------------------------------------------------------


def test_approve_proposal_returns_card_and_never_mutates():
    db = _FakeDB()
    db.proposals.seed(_proposal(status="pending_approval"))

    result = asyncio.run(dispatch_tool(db, "tenant-a", "u1", "approve_proposal", {"proposal_id": "p1"}))

    assert result["card"]["type"] == "approval_card"
    assert result["card"]["proposal_id"] == "p1"
    ApprovalCard(**result["card"])  # validates against the real schema

    # Nothing in the proposals collection was ever updated.
    assert db.proposals.update_calls == []
    stored = db.proposals.docs[0]
    assert stored["status"] == "pending_approval"


def test_existing_mode_approve_proposal_tool_call_produces_card_not_execution():
    db = _FakeDB()
    db.proposals.seed(_proposal(status="pending_approval"))

    mock_client = AsyncMock()
    mock_client.complete_with_tools.side_effect = [
        {"content": None, "tool_calls": [{"id": "call_1", "name": "approve_proposal", "arguments": {"proposal_id": "p1"}}]},
        {"content": "Here's the approval card — click Approve to confirm.", "tool_calls": []},
    ]

    with patch("services.chat.service.LLMClient", return_value=mock_client):
        response = asyncio.run(handle_chat_message(
            db, "tenant-a", "u1", _session(),
            ChatMessageRequest(session_id="s1", mode="existing", content="Approve p1"),
        ))

    assert len(response.cards) == 1
    assert isinstance(response.cards[0], ApprovalCard)
    assert db.proposals.update_calls == []  # the chat turn itself never mutated the proposal
    assert db.proposals.docs[0]["status"] == "pending_approval"


# ---------------------------------------------------------------------------
# Degrades cleanly when the LLM is unavailable
# ---------------------------------------------------------------------------


def test_existing_mode_degrades_cleanly_without_llm():
    db = _FakeDB()
    db.proposals.seed(_proposal())

    mock_client = AsyncMock()
    mock_client.complete_with_tools.side_effect = LLMUnavailable("no api key")

    with patch("services.chat.service.LLMClient", return_value=mock_client):
        response = asyncio.run(handle_chat_message(
            db, "tenant-a", "u1", _session(),
            ChatMessageRequest(session_id="s1", mode="existing", content="What did you find?"),
        ))

    assert response.content  # non-empty, real content from the fallback
    assert "i-1" in response.content or "stop_instance" in response.content
