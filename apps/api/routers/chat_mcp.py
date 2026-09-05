"""
Chatbot-only MCP bridge.

This is a small HTTP JSON-RPC adapter over services.chat.tools. It exposes
only the existing CloudCare chatbot tools, keeps every call tenant-scoped
from either the user's normal CloudCare login token or a server-side
CHATBOT_MCP_TOKEN, and never accepts tenant/user identity from MCP tool
arguments.
"""

from __future__ import annotations

import hashlib
import json
import secrets
from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials
from pydantic import BaseModel, Field

from apps.api.config import get_settings
from apps.api.db import get_db
from apps.api.dependencies import AuthenticatedUser, get_current_user
from services.llm.client import LLMClient, LLMUnavailable
from services.chat.tools import TOOL_SCHEMAS, UnknownToolError, dispatch_tool

router = APIRouter(prefix="/v1/chat/mcp", tags=["chat-mcp"])
_KNOWN_TOOL_NAMES = sorted(schema["function"]["name"] for schema in TOOL_SCHEMAS)
_TOKEN_PREFIX = "ccmcp_"
_RUNTIME_SETTING_KEYS = {
    "APP_ENV",
    "APP_BASE_URL",
    "CORS_ORIGINS",
    "MONGODB_URI",
    "MONGODB_DB_NAME",
    "OPENAI_API_KEY",
    "OPENAI_BASE_URL",
    "OPENAI_MODEL",
    "CHATBOT_MCP_ENABLED",
}
_SECRET_RUNTIME_KEYS = {"MONGODB_URI", "OPENAI_API_KEY"}


async def ensure_chat_mcp_indexes(db: Any) -> None:
    await db.chat_mcp_audit.create_index([("tenant_id", 1), ("created_at", -1)], name="tenant_created")
    await db.chat_mcp_audit.create_index([("tenant_id", 1), ("tool_name", 1)], name="tenant_tool")
    await db.chat_mcp_setups.create_index([("tenant_id", 1)], name="tenant_unique", unique=True)
    await db.chat_mcp_tokens.create_index([("token_hash", 1)], name="token_hash_unique", unique=True)
    await db.chat_mcp_tokens.create_index([("tenant_id", 1), ("created_at", -1)], name="tenant_token_created")
    await db.chat_mcp_runtime_settings.create_index([("tenant_id", 1)], name="tenant_unique", unique=True)


class JsonRpcRequest(BaseModel):
    jsonrpc: str = "2.0"
    id: str | int | None = None
    method: str
    params: dict[str, Any] = Field(default_factory=dict)


class ChatMcpSetupUpdate(BaseModel):
    enabled: bool = True
    client_name: str = Field(default="CloudCare Chatbot MCP", min_length=2, max_length=120)
    allowed_tools: list[str] = Field(default_factory=lambda: list(_KNOWN_TOOL_NAMES))
    instructions: str = Field(
        default=(
            "CloudCare chatbot may inspect tenant-scoped cost, proposal, and finding data. "
            "Execution approvals must stay explicit and user-confirmed."
        ),
        max_length=4000,
    )
    audit_enabled: bool = True


class ChatMcpTokenCreate(BaseModel):
    label: str = Field(default="Dashboard chatbot token", min_length=2, max_length=80)


class ChatMcpCheckRequest(BaseModel):
    run_model_probe: bool = False


class RuntimeSettingsUpdate(BaseModel):
    values: dict[str, str] = Field(default_factory=dict)


def _result(request_id: str | int | None, result: Any) -> dict[str, Any]:
    return {"jsonrpc": "2.0", "id": request_id, "result": result}


def _error(request_id: str | int | None, code: int, message: str, data: Any | None = None) -> dict[str, Any]:
    payload: dict[str, Any] = {"jsonrpc": "2.0", "id": request_id, "error": {"code": code, "message": message}}
    if data is not None:
        payload["error"]["data"] = data
    return payload


def _bearer_credentials(request: Request) -> HTTPAuthorizationCredentials | None:
    header = request.headers.get("authorization", "")
    if not header.lower().startswith("bearer "):
        return None
    return HTTPAuthorizationCredentials(scheme="Bearer", credentials=header[7:].strip())


def _hash_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def _new_token() -> str:
    return f"{_TOKEN_PREFIX}{secrets.token_urlsafe(32)}"


def _clean_allowed_tools(tool_names: list[str]) -> list[str]:
    clean = sorted({name for name in tool_names if name in _KNOWN_TOOL_NAMES})
    if not clean:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Select at least one valid MCP tool")
    return clean


def _serialize_doc(doc: dict[str, Any]) -> dict[str, Any]:
    return {k: v for k, v in doc.items() if k != "_id"}


def _mask_env_value(key: str, value: str) -> str:
    if key not in _SECRET_RUNTIME_KEYS:
        return value
    if not value:
        return ""
    if len(value) <= 10:
        return "***"
    return f"{value[:4]}...{value[-4:]}"


async def _tenant_runtime_settings(tenant_id: str) -> dict[str, str]:
    doc = await get_db().chat_mcp_runtime_settings.find_one({"tenant_id": tenant_id})
    values = (doc or {}).get("values") or {}
    return {key: str(values.get(key, "")) for key in _RUNTIME_SETTING_KEYS}


def _default_setup(tenant_id: str) -> dict[str, Any]:
    now = datetime.now(timezone.utc)
    return {
        "tenant_id": tenant_id,
        "enabled": True,
        "client_name": "CloudCare Chatbot MCP",
        "allowed_tools": list(_KNOWN_TOOL_NAMES),
        "instructions": (
            "CloudCare chatbot may inspect tenant-scoped cost, proposal, and finding data. "
            "Execution approvals must stay explicit and user-confirmed."
        ),
        "audit_enabled": True,
        "created_at": now,
        "updated_at": now,
        "configured_by": None,
    }


async def _tenant_setup(tenant_id: str) -> dict[str, Any]:
    doc = await get_db().chat_mcp_setups.find_one({"tenant_id": tenant_id})
    return _serialize_doc(doc) if doc else _default_setup(tenant_id)


async def _mcp_user(request: Request) -> AuthenticatedUser:
    settings = get_settings()
    if not settings.chatbot_mcp_enabled:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Chatbot MCP bridge is disabled")

    token = request.headers.get("x-cloudcare-mcp-token", "")
    if settings.chatbot_mcp_token and token and token == settings.chatbot_mcp_token:
        return {
            "user_id": settings.chatbot_mcp_user_id,
            "tenant_id": settings.chatbot_mcp_tenant_id,
            "email": settings.chatbot_mcp_user_email or None,
            "full_name": "CloudCare Chatbot MCP",
        }

    if token:
        token_doc = await get_db().chat_mcp_tokens.find_one({"token_hash": _hash_token(token), "revoked_at": None})
        if token_doc:
            await get_db().chat_mcp_tokens.update_one(
                {"token_hash": _hash_token(token)},
                {"$set": {"last_used_at": datetime.now(timezone.utc)}},
            )
            return {
                "user_id": token_doc.get("user_id") or "chatbot-mcp",
                "tenant_id": token_doc["tenant_id"],
                "email": token_doc.get("email"),
                "full_name": token_doc.get("client_name") or "CloudCare Chatbot MCP",
            }

    return await get_current_user(request, _bearer_credentials(request))


def _mcp_tools(allowed_tools: list[str] | None = None) -> list[dict[str, Any]]:
    allowed = set(allowed_tools or _KNOWN_TOOL_NAMES)
    tools: list[dict[str, Any]] = []
    for schema in TOOL_SCHEMAS:
        fn = schema["function"]
        if fn["name"] not in allowed:
            continue
        tools.append(
            {
                "name": fn["name"],
                "description": fn["description"],
                "inputSchema": fn["parameters"],
            }
        )
    return tools


async def _call_tool(user: AuthenticatedUser, params: dict[str, Any]) -> dict[str, Any]:
    name = params.get("name")
    arguments = params.get("arguments") or {}
    if not isinstance(name, str):
        raise ValueError("tools/call requires params.name")
    if not isinstance(arguments, dict):
        raise ValueError("tools/call params.arguments must be an object")

    setup = await _tenant_setup(user["tenant_id"])
    if not setup.get("enabled", True):
        raise ValueError("Chatbot MCP is disabled for this tenant")
    if name not in set(setup.get("allowed_tools") or _KNOWN_TOOL_NAMES):
        raise ValueError(f"MCP tool is not enabled for this tenant: {name}")

    result = await dispatch_tool(get_db(), user["tenant_id"], user["user_id"], name, arguments)
    return {
        "content": [
            {
                "type": "text",
                "text": json.dumps(result, default=str, separators=(",", ":")),
            }
        ],
        "structuredContent": result,
        "isError": bool(isinstance(result, dict) and result.get("error")),
    }


async def _record_mcp_audit(
    *,
    user: AuthenticatedUser,
    method: str,
    tool_name: str | None,
    ok: bool,
    error: str | None = None,
) -> None:
    try:
        setup = await _tenant_setup(user["tenant_id"])
        if not setup.get("audit_enabled", True):
            return
        await get_db().chat_mcp_audit.insert_one(
            {
                "tenant_id": user["tenant_id"],
                "user_id": user["user_id"],
                "method": method,
                "tool_name": tool_name,
                "ok": ok,
                "error": error,
                "created_at": datetime.now(timezone.utc),
            }
        )
    except Exception:
        # MCP must stay fast and available even if audit persistence is briefly down.
        return


def _status(settings: Any, setup: dict[str, Any], token_count: int, audit_count: int, runtime_values: dict[str, str] | None = None) -> dict[str, Any]:
    runtime_values = runtime_values or {}
    return {
        "mcp_enabled": bool(str(runtime_values.get("CHATBOT_MCP_ENABLED") or settings.chatbot_mcp_enabled).lower() != "false" and setup.get("enabled", True)),
        "env_token_configured": bool(settings.chatbot_mcp_token),
        "dashboard_tokens": token_count,
        "mongo_audit_events": audit_count,
        "model_configured": bool(runtime_values.get("OPENAI_API_KEY") or settings.openai_api_key),
        "model": runtime_values.get("OPENAI_MODEL") or settings.openai_model,
        "model_base_url": runtime_values.get("OPENAI_BASE_URL") or settings.openai_base_url,
        "allowed_tool_count": len(setup.get("allowed_tools") or []),
        "chatbot_only_scope": True,
    }


async def _setup_response(user: AuthenticatedUser) -> dict[str, Any]:
    db = get_db()
    settings = get_settings()
    setup = await _tenant_setup(user["tenant_id"])
    runtime_values = await _tenant_runtime_settings(user["tenant_id"])
    tokens = await db.chat_mcp_tokens.find({"tenant_id": user["tenant_id"], "revoked_at": None}).sort("created_at", -1).to_list(50)
    audit = await db.chat_mcp_audit.find({"tenant_id": user["tenant_id"]}).sort("created_at", -1).limit(25).to_list(25)
    token_docs = [_serialize_doc(doc) for doc in tokens]
    audit_docs = [_serialize_doc(doc) for doc in audit]
    return {
        "setup": setup,
        "available_tools": _mcp_tools(),
        "tokens": [
            {
                "token_id": doc.get("token_id"),
                "label": doc.get("label"),
                "created_at": doc.get("created_at"),
                "created_by": doc.get("created_by"),
                "last_used_at": doc.get("last_used_at"),
            }
            for doc in token_docs
        ],
        "audit": audit_docs,
        "status": _status(settings, setup, len(token_docs), len(audit_docs), runtime_values),
    }


def _runtime_response(doc: dict[str, Any] | None, tenant_id: str) -> dict[str, Any]:
    values = {key: "" for key in sorted(_RUNTIME_SETTING_KEYS)}
    if doc:
        values.update({key: str(value) for key, value in (doc.get("values") or {}).items() if key in _RUNTIME_SETTING_KEYS})
    return {
        "tenant_id": tenant_id,
        "storage": "mongodb",
        "collection": "chat_mcp_runtime_settings",
        "bootstrap_note": "Backend still needs an initial MongoDB connection before it can read settings from MongoDB.",
        "allowed_keys": sorted(_RUNTIME_SETTING_KEYS),
        "values": {key: _mask_env_value(key, values.get(key, "")) for key in sorted(_RUNTIME_SETTING_KEYS)},
        "configured": {key: bool(values.get(key, "")) for key in sorted(_RUNTIME_SETTING_KEYS)},
        "updated_at": doc.get("updated_at") if doc else None,
        "updated_by": doc.get("updated_by") if doc else None,
    }


def _effective_llm_settings(settings: Any, runtime_values: dict[str, str]) -> Any:
    overrides = {
        "openai_api_key": runtime_values.get("OPENAI_API_KEY") or settings.openai_api_key,
        "openai_base_url": runtime_values.get("OPENAI_BASE_URL") or settings.openai_base_url,
        "openai_model": runtime_values.get("OPENAI_MODEL") or settings.openai_model,
    }
    if hasattr(settings, "model_copy"):
        return settings.model_copy(update=overrides)
    for key, value in overrides.items():
        setattr(settings, key, value)
    return settings


@router.get("/setup", response_model=dict[str, Any])
async def get_chat_mcp_setup(current_user: AuthenticatedUser = Depends(get_current_user)) -> dict[str, Any]:
    return await _setup_response(current_user)


@router.post("/setup", response_model=dict[str, Any])
async def save_chat_mcp_setup(
    payload: ChatMcpSetupUpdate,
    current_user: AuthenticatedUser = Depends(get_current_user),
) -> dict[str, Any]:
    now = datetime.now(timezone.utc)
    allowed_tools = _clean_allowed_tools(payload.allowed_tools)
    doc = {
        "tenant_id": current_user["tenant_id"],
        "enabled": payload.enabled,
        "client_name": payload.client_name,
        "allowed_tools": allowed_tools,
        "instructions": payload.instructions,
        "audit_enabled": payload.audit_enabled,
        "configured_by": current_user["user_id"],
        "updated_at": now,
    }
    await get_db().chat_mcp_setups.update_one(
        {"tenant_id": current_user["tenant_id"]},
        {"$set": doc, "$setOnInsert": {"created_at": now}},
        upsert=True,
    )
    await _record_mcp_audit(user=current_user, method="setup/save", tool_name=None, ok=True)
    return await _setup_response(current_user)


@router.get("/setup/runtime-settings", response_model=dict[str, Any])
async def get_runtime_settings(current_user: AuthenticatedUser = Depends(get_current_user)) -> dict[str, Any]:
    doc = await get_db().chat_mcp_runtime_settings.find_one({"tenant_id": current_user["tenant_id"]})
    return _runtime_response(doc, current_user["tenant_id"])


@router.post("/setup/runtime-settings", response_model=dict[str, Any])
async def save_runtime_settings(
    payload: RuntimeSettingsUpdate,
    current_user: AuthenticatedUser = Depends(get_current_user),
) -> dict[str, Any]:
    unknown = sorted(set(payload.values) - _RUNTIME_SETTING_KEYS)
    if unknown:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Unsupported setting keys: {', '.join(unknown)}")
    values = {key: str(value).strip() for key, value in payload.values.items() if key in _RUNTIME_SETTING_KEYS}
    if not values:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="No runtime settings supplied")
    now = datetime.now(timezone.utc)
    existing = await _tenant_runtime_settings(current_user["tenant_id"])
    merged = {**existing, **values}
    await get_db().chat_mcp_runtime_settings.update_one(
        {"tenant_id": current_user["tenant_id"]},
        {
            "$set": {
                "tenant_id": current_user["tenant_id"],
                "values": merged,
                "updated_by": current_user["user_id"],
                "updated_at": now,
            },
            "$setOnInsert": {"created_at": now},
        },
        upsert=True,
    )
    await _record_mcp_audit(user=current_user, method="setup/runtime_settings_saved", tool_name=None, ok=True)
    doc = await get_db().chat_mcp_runtime_settings.find_one({"tenant_id": current_user["tenant_id"]})
    return _runtime_response(doc, current_user["tenant_id"])


@router.post("/setup/token", response_model=dict[str, Any])
async def create_chat_mcp_token(
    payload: ChatMcpTokenCreate,
    current_user: AuthenticatedUser = Depends(get_current_user),
) -> dict[str, Any]:
    token = _new_token()
    token_id = secrets.token_hex(8)
    setup = await _tenant_setup(current_user["tenant_id"])
    now = datetime.now(timezone.utc)
    await get_db().chat_mcp_tokens.insert_one(
        {
            "tenant_id": current_user["tenant_id"],
            "token_id": token_id,
            "token_hash": _hash_token(token),
            "label": payload.label,
            "client_name": setup.get("client_name") or "CloudCare Chatbot MCP",
            "user_id": "chatbot-mcp",
            "email": current_user.get("email"),
            "created_by": current_user["user_id"],
            "created_at": now,
            "last_used_at": None,
            "revoked_at": None,
        }
    )
    await _record_mcp_audit(user=current_user, method="setup/token_created", tool_name=None, ok=True)
    response = await _setup_response(current_user)
    response["token"] = token
    response["token_id"] = token_id
    return response


@router.post("/setup/check", response_model=dict[str, Any])
async def check_chat_mcp_setup(
    payload: ChatMcpCheckRequest,
    current_user: AuthenticatedUser = Depends(get_current_user),
) -> dict[str, Any]:
    settings = get_settings()
    setup = await _tenant_setup(current_user["tenant_id"])
    runtime_values = await _tenant_runtime_settings(current_user["tenant_id"])
    effective_settings = _effective_llm_settings(settings, runtime_values)
    checks = [
        {"key": "mcp_enabled", "ok": bool(str(runtime_values.get("CHATBOT_MCP_ENABLED") or settings.chatbot_mcp_enabled).lower() != "false" and setup.get("enabled")), "detail": "MCP route and tenant setup are enabled."},
        {"key": "tenant_scope", "ok": True, "detail": "MCP tool calls derive tenant/user identity from CloudCare auth or stored token hash."},
        {"key": "allowed_tools", "ok": bool(setup.get("allowed_tools")), "detail": f"{len(setup.get('allowed_tools') or [])} tool(s) enabled."},
        {"key": "mongo_persistence", "ok": True, "detail": "Setup, token metadata, and audits are written to MongoDB collections."},
        {"key": "ai_model_mongodb", "ok": bool(effective_settings.openai_api_key), "detail": f"Model: {effective_settings.openai_model}"},
    ]
    ai_review: dict[str, Any] | None = None
    if payload.run_model_probe and effective_settings.openai_api_key:
        try:
            ai_review = await LLMClient(effective_settings).complete(
                system="You are a CloudCare setup auditor. Return compact JSON only.",
                user=json.dumps({"setup": setup, "checks": checks}, default=str),
                json_schema={
                    "name": "cloudcare_mcp_setup_review",
                    "schema": {
                        "type": "object",
                        "properties": {
                            "ready": {"type": "boolean"},
                            "summary": {"type": "string"},
                            "next_actions": {"type": "array", "items": {"type": "string"}},
                        },
                        "required": ["ready", "summary", "next_actions"],
                        "additionalProperties": False,
                    },
                },
            )
            checks.append({"key": "ai_probe", "ok": True, "detail": "AI model completed a setup review."})
        except (LLMUnavailable, Exception) as exc:  # noqa: BLE001 - health checks should report, not crash
            checks.append({"key": "ai_probe", "ok": False, "detail": str(exc)[:240]})
    await _record_mcp_audit(user=current_user, method="setup/check", tool_name=None, ok=all(c["ok"] for c in checks))
    return {"checked_at": datetime.now(timezone.utc), "checks": checks, "ai_review": ai_review}


@router.post("", response_model=dict[str, Any])
async def chatbot_mcp(payload: JsonRpcRequest, request: Request) -> dict[str, Any]:
    user = await _mcp_user(request)
    tool_name = payload.params.get("name") if isinstance(payload.params.get("name"), str) else None

    if payload.method == "initialize":
        await _record_mcp_audit(user=user, method=payload.method, tool_name=None, ok=True)
        return _result(
            payload.id,
            {
                "protocolVersion": "2024-11-05",
                "serverInfo": {"name": "cloudcare-chatbot-mcp", "version": "1.0.0"},
                "capabilities": {"tools": {"listChanged": False}},
                "instructions": (
                    "Use only these CloudCare chatbot tools. All data is tenant-scoped by the authenticated "
                    "CloudCare user or CHATBOT_MCP_TOKEN env identity. Never pass tenant_id or user_id in tool arguments."
                ),
            },
        )

    if payload.method == "ping":
        await _record_mcp_audit(user=user, method=payload.method, tool_name=None, ok=True)
        return _result(payload.id, {})

    if payload.method == "tools/list":
        await _record_mcp_audit(user=user, method=payload.method, tool_name=None, ok=True)
        setup = await _tenant_setup(user["tenant_id"])
        if not setup.get("enabled", True):
            return _result(payload.id, {"tools": []})
        return _result(payload.id, {"tools": _mcp_tools(setup.get("allowed_tools"))})

    if payload.method == "tools/call":
        try:
            result = await _call_tool(user, payload.params)
            await _record_mcp_audit(user=user, method=payload.method, tool_name=tool_name, ok=not result["isError"])
            return _result(payload.id, result)
        except UnknownToolError as exc:
            await _record_mcp_audit(user=user, method=payload.method, tool_name=tool_name, ok=False, error=str(exc))
            return _error(payload.id, -32602, str(exc))
        except ValueError as exc:
            await _record_mcp_audit(user=user, method=payload.method, tool_name=tool_name, ok=False, error=str(exc))
            return _error(payload.id, -32602, str(exc))

    if payload.method.startswith("notifications/"):
        await _record_mcp_audit(user=user, method=payload.method, tool_name=None, ok=True)
        return _result(payload.id, {})

    await _record_mcp_audit(user=user, method=payload.method, tool_name=tool_name, ok=False, error="unsupported_method")
    return _error(payload.id, -32601, f"Unsupported MCP method: {payload.method}")
