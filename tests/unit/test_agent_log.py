from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import services.agent_log as agent_log


def _mock_db():
    mock_db = MagicMock()
    mock_collection = MagicMock()
    mock_collection.insert_one = AsyncMock()
    mock_collection.create_index = AsyncMock()
    mock_collection.find = MagicMock()
    mock_db.__getitem__.return_value = mock_collection
    return mock_db, mock_collection


def test_ensure_indexes_creates_tenant_run_started_index():
    mock_db, mock_collection = _mock_db()

    asyncio.run(agent_log.ensure_indexes(mock_db))

    mock_collection.create_index.assert_awaited_once_with(
        [("tenant_id", 1), ("run_id", 1), ("started_at", -1)],
        name="tenant_run_started",
    )


@patch("services.agent_log.get_db")
def test_log_agent_run_writes_expected_document(mock_get_db):
    mock_db, mock_collection = _mock_db()
    mock_get_db.return_value = mock_db

    started_at = datetime(2026, 1, 1, 10, 0, 0, tzinfo=timezone.utc)
    finished_at = started_at + timedelta(seconds=2, milliseconds=500)

    log_id = asyncio.run(
        agent_log.log_agent_run(
            tenant_id="demo-tenant",
            run_id="run-123",
            agent="Monitor",
            status="success",
            started_at=started_at,
            finished_at=finished_at,
            input_summary={"account_id": "123"},
            output_summary={"message": "Collected 5 resources"},
            payload={"resources": 5},
            error=None,
        )
    )

    mock_collection.insert_one.assert_awaited_once()
    doc = mock_collection.insert_one.await_args.args[0]

    assert doc["log_id"] == log_id
    assert doc["tenant_id"] == "demo-tenant"
    assert doc["run_id"] == "run-123"
    assert doc["agent"] == "Monitor"
    assert doc["status"] == "success"
    assert doc["started_at"] == started_at
    assert doc["finished_at"] == finished_at
    assert doc["duration_ms"] == 2500
    assert doc["input_summary"] == {"account_id": "123"}
    assert doc["output_summary"] == {"message": "Collected 5 resources"}
    assert doc["payload"] == {"resources": 5}
    assert doc["error"] is None


@patch("services.agent_log.get_db")
def test_log_agent_run_records_failure_with_error(mock_get_db):
    mock_db, mock_collection = _mock_db()
    mock_get_db.return_value = mock_db

    started_at = datetime(2026, 1, 1, 10, 0, 0, tzinfo=timezone.utc)
    finished_at = started_at + timedelta(seconds=1)

    asyncio.run(
        agent_log.log_agent_run(
            tenant_id="demo-tenant",
            run_id="run-456",
            agent="Executor",
            status="failed",
            started_at=started_at,
            finished_at=finished_at,
            input_summary={},
            output_summary={"message": "boom"},
            payload={},
            error="ConnectionError: timed out",
        )
    )

    doc = mock_collection.insert_one.await_args.args[0]
    assert doc["status"] == "failed"
    assert doc["error"] == "ConnectionError: timed out"
    assert doc["agent"] == "Executor"


@patch("services.agent_log.get_db")
def test_list_agent_runs_filters_by_tenant_run_and_agent(mock_get_db):
    mock_db, mock_collection = _mock_db()
    mock_get_db.return_value = mock_db

    fake_cursor = MagicMock()
    fake_cursor.sort.return_value = fake_cursor
    fake_cursor.limit.return_value = fake_cursor
    fake_cursor.to_list = AsyncMock(return_value=[{"agent": "Monitor"}])
    mock_collection.find.return_value = fake_cursor

    result = asyncio.run(
        agent_log.list_agent_runs(tenant_id="demo-tenant", run_id="run-123", agent="Monitor", limit=50)
    )

    mock_collection.find.assert_called_once_with(
        {"tenant_id": "demo-tenant", "run_id": "run-123", "agent": "Monitor"}, {"_id": 0}
    )
    fake_cursor.sort.assert_called_once_with("started_at", -1)
    fake_cursor.limit.assert_called_once_with(50)
    assert result == [{"agent": "Monitor"}]
