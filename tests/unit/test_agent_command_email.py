from __future__ import annotations

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

from fastapi import BackgroundTasks

from apps.api.routers import agent_command
from services.notifications.email import build_agent_command_analysis_email_html


def _run_doc() -> dict:
    return {
        "run_id": "run-123",
        "status": "success",
        "provider": "aws",
        "account_id": "acct-1",
        "region": "ap-south-1",
        "summary": {
            "resources": 4,
            "findings": 2,
            "proposals": 1,
            "pending_approvals": 1,
            "blocked": 0,
            "potential_monthly_savings": 42,
            "executed_or_simulated": 0,
        },
        "steps": [
            {
                "name": "Decision Agent",
                "status": "success",
                "summary": "Built 1 action proposal.",
                "metrics": [{"label": "LLM used", "value": "yes"}],
            }
        ],
        "proposals": [
            {
                "action_type": "stop_instance",
                "status": "pending_approval",
                "expected_monthly_savings": "42.00",
                "risk_level": "low",
                "rationale": "Idle development instance.",
            }
        ],
        "executions": [],
    }


def _successful_send(*_args):
    return {"sent": True, "provider": "brevo", "errors": []}


def test_agent_command_analysis_template_includes_agent_decisions_and_escapes_html():
    doc = _run_doc()
    doc["steps"][0]["summary"] = "<script>alert('x')</script>"

    html = build_agent_command_analysis_email_html(
        {
            **doc,
            "dashboard_url": "http://localhost:3000/dashboard/agent-command?run_id=run-123",
        }
    )

    assert "Agent Command Analysis Complete" in html
    assert "Decision Agent" in html
    assert "alert(&#x27;x&#x27;)" in html
    assert "&lt;script&gt;" in html
    assert "<script>" not in html
    assert "stop_instance" in html
    assert "$42.00/mo" in html


def test_dispatch_agent_command_analysis_email_uses_current_user_email_without_db_lookup():
    db = MagicMock()
    db.users.find_one = AsyncMock()
    tasks = BackgroundTasks()
    settings = SimpleNamespace(app_base_url="http://localhost:3000")
    current_user = {"tenant_id": "demo-tenant", "email": "owner@example.com"}

    with patch("apps.api.routers.agent_command.get_settings", return_value=settings), patch(
        "apps.api.routers.agent_command.send_agent_command_analysis_email_status_sync", side_effect=_successful_send
    ) as mock_send:
        result = asyncio.run(agent_command._dispatch_agent_command_analysis_email(db, tasks, current_user, _run_doc()))

    db.users.find_one.assert_not_called()
    assert len(tasks.tasks) == 0
    assert result == {
        "attempted": True,
        "sent": True,
        "recipient": "ow***r@example.com",
        "reason": None,
        "provider": "brevo",
        "errors": [],
    }
    assert mock_send.call_args.args[0] == "owner@example.com"
    assert mock_send.call_args.args[1]["run_id"] == "run-123"
    assert mock_send.call_args.args[1]["dashboard_url"].endswith("?run_id=run-123")


def test_dispatch_agent_command_analysis_email_falls_back_to_tenant_user():
    db = MagicMock()
    db.users.find_one = AsyncMock(return_value={"email": "tenant@example.com"})
    settings = SimpleNamespace(app_base_url="http://localhost:3000")
    current_user = {"tenant_id": "demo-tenant", "email": None}

    with patch("apps.api.routers.agent_command.get_settings", return_value=settings), patch(
        "apps.api.routers.agent_command.send_agent_command_analysis_email_status_sync", side_effect=_successful_send
    ) as mock_send:
        result = asyncio.run(agent_command._dispatch_agent_command_analysis_email(db, None, current_user, _run_doc()))

    db.users.find_one.assert_awaited_once_with({"tenant_id": "demo-tenant"}, {"_id": 0, "email": 1})
    mock_send.assert_called_once()
    assert mock_send.call_args.args[0] == "tenant@example.com"
    assert result["sent"] is True
    assert result["recipient"] == "te***t@example.com"


def test_dispatch_agent_command_analysis_email_prefers_tenant_email_for_dev_fallback_user():
    db = MagicMock()
    db.users.find_one = AsyncMock(return_value={"email": "tenant@example.com"})
    settings = SimpleNamespace(app_base_url="http://localhost:3000")
    current_user = {"tenant_id": "demo-tenant", "email": "demo@cloudcare.ai"}

    with patch("apps.api.routers.agent_command.get_settings", return_value=settings), patch(
        "apps.api.routers.agent_command.send_agent_command_analysis_email_status_sync", side_effect=_successful_send
    ) as mock_send:
        result = asyncio.run(agent_command._dispatch_agent_command_analysis_email(db, None, current_user, _run_doc()))

    db.users.find_one.assert_awaited_once_with({"tenant_id": "demo-tenant"}, {"_id": 0, "email": 1})
    assert mock_send.call_args.args[0] == "tenant@example.com"
    assert result["recipient"] == "te***t@example.com"


def test_dispatch_agent_command_analysis_email_prefers_cloudcare_user_record():
    db = MagicMock()
    db.users.find_one = AsyncMock(side_effect=[{"email": "owner@example.com"}])
    settings = SimpleNamespace(app_base_url="http://localhost:3000")
    current_user = {"user_id": "demo.user", "tenant_id": "demo-tenant", "email": "demo@cloudcare.ai"}

    with patch("apps.api.routers.agent_command.get_settings", return_value=settings), patch(
        "apps.api.routers.agent_command.send_agent_command_analysis_email_status_sync", side_effect=_successful_send
    ) as mock_send:
        result = asyncio.run(agent_command._dispatch_agent_command_analysis_email(db, None, current_user, _run_doc()))

    db.users.find_one.assert_awaited_once_with({"user_id": "demo.user"}, {"_id": 0, "email": 1})
    assert mock_send.call_args.args[0] == "owner@example.com"
    assert result["recipient"] == "ow***r@example.com"


def test_persist_run_notifications_updates_saved_command_run():
    db = MagicMock()
    collection = MagicMock()
    collection.update_one = AsyncMock()
    db.__getitem__.return_value = collection
    notifications = {
        "agent_command_analysis_email": {
            "attempted": True,
            "sent": True,
            "recipient": "ow***r@example.com",
            "reason": None,
            "provider": "brevo",
            "errors": [],
        }
    }

    asyncio.run(
        agent_command._persist_run_notifications(
            db,
            tenant_id="demo-tenant",
            run_id="run-123",
            notifications=notifications,
        )
    )

    collection.update_one.assert_awaited_once()
    query, update = collection.update_one.await_args.args
    assert query == {"tenant_id": "demo-tenant", "run_id": "run-123"}
    assert update["$set"]["notifications"] == notifications
    assert "updated_at" in update["$set"]
