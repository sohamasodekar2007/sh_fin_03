from __future__ import annotations

from unittest.mock import patch

from fastapi.testclient import TestClient

from apps.api.main import app
from apps.api.security import create_access_token
from services.chat.tools import TOOL_SCHEMAS
from tests.unit.test_chat_router import _FakeDB, _proposal


def _client(db: _FakeDB):
    return TestClient(app), patch("apps.api.routers.chat_mcp.get_db", return_value=db)


def test_chat_mcp_lists_tools_with_env_token():
    db = _FakeDB()
    client, db_patch = _client(db)
    settings_patch = patch(
        "apps.api.routers.chat_mcp.get_settings",
        return_value=type(
            "Settings",
            (),
            {
                "chatbot_mcp_enabled": True,
                "chatbot_mcp_token": "secret-token",
                "chatbot_mcp_tenant_id": "tenant-a",
                "chatbot_mcp_user_id": "mcp-user",
                "chatbot_mcp_user_email": "mcp@example.com",
            },
        )(),
    )

    with db_patch, settings_patch:
        response = client.post(
            "/v1/chat/mcp",
            headers={"x-cloudcare-mcp-token": "secret-token"},
            json={"jsonrpc": "2.0", "id": 1, "method": "tools/list"},
        )

    assert response.status_code == 200
    data = response.json()
    assert data["result"]["tools"]
    assert data["result"]["tools"][0]["inputSchema"]["type"] == "object"
    assert db.chat_mcp_audit.docs[0]["tenant_id"] == "tenant-a"
    assert db.chat_mcp_audit.docs[0]["method"] == "tools/list"


def test_chat_mcp_calls_existing_tool_with_login_jwt_and_tenant_scope():
    db = _FakeDB()
    db.users.seed({"user_id": "u1", "tenant_id": "tenant-a", "email": "u1@example.com"})
    db.proposals.seed(_proposal(tenant_id="tenant-a"), _proposal(tenant_id="tenant-b"))
    client, db_patch = _client(db)
    token = create_access_token("u1", "tenant-a")

    with db_patch, patch("apps.api.dependencies.get_db", return_value=db):
        response = client.post(
            "/v1/chat/mcp",
            headers={"Authorization": f"Bearer {token}"},
            json={
                "jsonrpc": "2.0",
                "id": "call-1",
                "method": "tools/call",
                "params": {"name": "get_proposal_details", "arguments": {"proposal_id": "p1"}},
            },
        )

    assert response.status_code == 200
    result = response.json()["result"]
    assert result["structuredContent"]["tenant_id"] == "tenant-a"
    assert result["isError"] is False
    assert db.chat_mcp_audit.docs[-1]["tool_name"] == "get_proposal_details"


def test_chat_mcp_rejects_unknown_tool():
    db = _FakeDB()
    client, db_patch = _client(db)
    settings_patch = patch(
        "apps.api.routers.chat_mcp.get_settings",
        return_value=type(
            "Settings",
            (),
            {
                "chatbot_mcp_enabled": True,
                "chatbot_mcp_token": "secret-token",
                "chatbot_mcp_tenant_id": "tenant-a",
                "chatbot_mcp_user_id": "mcp-user",
                "chatbot_mcp_user_email": "",
            },
        )(),
    )

    with db_patch, settings_patch:
        response = client.post(
            "/v1/chat/mcp",
            headers={"x-cloudcare-mcp-token": "secret-token"},
            json={
                "jsonrpc": "2.0",
                "id": 2,
                "method": "tools/call",
                "params": {"name": "delete_everything", "arguments": {}},
            },
        )

    assert response.status_code == 200
    assert response.json()["error"]["code"] == -32602
    assert db.chat_mcp_audit.docs[-1]["ok"] is False


def test_chat_mcp_setup_save_generates_db_token_and_limits_tools():
    db = _FakeDB()
    db.users.seed({"user_id": "u1", "tenant_id": "tenant-a", "email": "u1@example.com"})
    client, db_patch = _client(db)
    token = create_access_token("u1", "tenant-a")

    with db_patch, patch("apps.api.dependencies.get_db", return_value=db):
        save_response = client.post(
            "/v1/chat/mcp/setup",
            headers={"Authorization": f"Bearer {token}"},
            json={
                "enabled": True,
                "client_name": "CloudCare Frontend Chatbot",
                "allowed_tools": ["get_cost_summary"],
                "instructions": "Answer only from CloudCare tenant data.",
                "audit_enabled": True,
            },
        )
        token_response = client.post(
            "/v1/chat/mcp/setup/token",
            headers={"Authorization": f"Bearer {token}"},
            json={"label": "frontend test token"},
        )
        mcp_token = token_response.json()["token"]
        list_response = client.post(
            "/v1/chat/mcp",
            headers={"x-cloudcare-mcp-token": mcp_token},
            json={"jsonrpc": "2.0", "id": "tools", "method": "tools/list"},
        )

    assert save_response.status_code == 200
    assert token_response.status_code == 200
    assert mcp_token.startswith("ccmcp_")
    assert db.chat_mcp_tokens.docs[0]["token_hash"] != mcp_token
    tools = list_response.json()["result"]["tools"]
    assert [tool["name"] for tool in tools] == ["get_cost_summary"]


def test_chat_mcp_setup_rejects_invalid_allowed_tools():
    db = _FakeDB()
    db.users.seed({"user_id": "u1", "tenant_id": "tenant-a", "email": "u1@example.com"})
    client, db_patch = _client(db)
    token = create_access_token("u1", "tenant-a")

    with db_patch, patch("apps.api.dependencies.get_db", return_value=db):
        response = client.post(
            "/v1/chat/mcp/setup",
            headers={"Authorization": f"Bearer {token}"},
            json={
                "enabled": True,
                "client_name": "CloudCare Frontend Chatbot",
                "allowed_tools": ["delete_everything"],
                "instructions": "Answer only from CloudCare tenant data.",
                "audit_enabled": True,
            },
        )

    assert response.status_code == 400


def test_chat_mcp_setup_check_reports_model_status_without_probe():
    db = _FakeDB()
    db.users.seed({"user_id": "u1", "tenant_id": "tenant-a", "email": "u1@example.com"})
    client, db_patch = _client(db)
    token = create_access_token("u1", "tenant-a")

    with db_patch, patch("apps.api.dependencies.get_db", return_value=db):
        response = client.post(
            "/v1/chat/mcp/setup/check",
            headers={"Authorization": f"Bearer {token}"},
            json={"run_model_probe": False},
        )

    assert response.status_code == 200
    checks = {check["key"]: check for check in response.json()["checks"]}
    assert checks["tenant_scope"]["ok"] is True
    assert "ai_model_mongodb" in checks
    assert len(TOOL_SCHEMAS) >= 1


def test_chat_mcp_runtime_settings_save_to_mongodb_and_mask_secrets():
    db = _FakeDB()
    db.users.seed({"user_id": "u1", "tenant_id": "tenant-a", "email": "u1@example.com"})
    client, db_patch = _client(db)
    token = create_access_token("u1", "tenant-a")

    with db_patch, patch("apps.api.dependencies.get_db", return_value=db):
        response = client.post(
            "/v1/chat/mcp/setup/runtime-settings",
            headers={"Authorization": f"Bearer {token}"},
            json={
                "values": {
                    "APP_BASE_URL": "http://localhost:3002",
                    "OPENAI_API_KEY": "secret-model-key",
                    "OPENAI_MODEL": "gpt-5.6-sol",
                    "MONGODB_DB_NAME": "cloudcare",
                }
            },
        )

    assert response.status_code == 200
    assert db.chat_mcp_runtime_settings.docs[0]["values"]["OPENAI_API_KEY"] == "secret-model-key"
    assert response.json()["values"]["OPENAI_API_KEY"].startswith("secr...")
    assert response.json()["collection"] == "chat_mcp_runtime_settings"


def test_chat_mcp_runtime_settings_rejects_unknown_key():
    db = _FakeDB()
    db.users.seed({"user_id": "u1", "tenant_id": "tenant-a", "email": "u1@example.com"})
    client, db_patch = _client(db)
    token = create_access_token("u1", "tenant-a")

    with db_patch, patch("apps.api.dependencies.get_db", return_value=db):
        response = client.post(
            "/v1/chat/mcp/setup/runtime-settings",
            headers={"Authorization": f"Bearer {token}"},
            json={"values": {"AWS_SECRET_ACCESS_KEY": "nope"}},
        )

    assert response.status_code == 400
