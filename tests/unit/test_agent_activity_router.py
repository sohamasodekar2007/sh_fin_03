from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import AsyncMock, patch

from fastapi.testclient import TestClient

from apps.api.main import app

client = TestClient(app)


def test_list_agent_activity_reads_from_agent_runs_not_mock_constant():
    fake_runs = [
        {
            "log_id": "log-1",
            "agent": "Monitor",
            "status": "success",
            "started_at": datetime(2026, 1, 1, 10, 2, 14, tzinfo=timezone.utc),
            "output_summary": {"message": "Collected 24 resources, 720 FOCUS rows (live)"},
        },
        {
            "log_id": "log-2",
            "agent": "Executor",
            "status": "failed",
            "started_at": datetime(2026, 1, 1, 10, 3, 0, tzinfo=timezone.utc),
            "output_summary": {},
            "error": "boom",
        },
    ]

    with patch("apps.api.routers.agent_activity.list_agent_runs", new_callable=AsyncMock) as mock_list:
        mock_list.return_value = fake_runs
        response = client.get(
            "/v1/agent-activity",
            headers={"Authorization": "Bearer fake-token-in-dev-mode"},
        )

    assert response.status_code == 200
    entries = response.json()
    assert len(entries) == 2

    assert entries[0]["id"] == "log-1"
    assert entries[0]["agent"] == "Monitor"
    assert entries[0]["message"] == "Collected 24 resources, 720 FOCUS rows (live)"
    assert entries[0]["timestamp"] == "10:02:14"

    # A failed run with no output_summary message falls back to a generated one.
    assert entries[1]["agent"] == "Executor"
    assert "failed" in entries[1]["message"].lower()
    assert "boom" in entries[1]["message"]


def test_list_agent_activity_passes_filters_through():
    with patch("apps.api.routers.agent_activity.list_agent_runs", new_callable=AsyncMock) as mock_list:
        mock_list.return_value = []
        client.get(
            "/v1/agent-activity?run_id=run-123&agent=Decision&limit=10",
            headers={"Authorization": "Bearer fake-token-in-dev-mode"},
        )

    mock_list.assert_awaited_once()
    kwargs = mock_list.await_args.kwargs
    assert kwargs["run_id"] == "run-123"
    assert kwargs["agent"] == "Decision"
    assert kwargs["limit"] == 10
