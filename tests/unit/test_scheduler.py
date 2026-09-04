from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import services.scheduler as scheduler


def _mock_db():
    mock_db = MagicMock()
    mock_collection = MagicMock()
    mock_collection.create_index = AsyncMock()
    mock_collection.insert_one = AsyncMock()
    mock_collection.delete_one = AsyncMock()
    mock_collection.update_one = AsyncMock()
    mock_collection.find_one = AsyncMock(return_value=None)

    def _getitem(name):
        return mock_collection

    mock_db.__getitem__.side_effect = _getitem
    mock_db.cloud_accounts = MagicMock()
    mock_db.proposals = mock_collection
    mock_db.cloud_snapshots = mock_collection
    return mock_db, mock_collection


# ---------------------------------------------------------------------------
# Lock index setup
# ---------------------------------------------------------------------------


def test_ensure_lock_index_creates_ttl_and_unique_indexes():
    mock_db, mock_collection = _mock_db()

    asyncio.run(scheduler.ensure_lock_index(mock_db))

    assert mock_collection.create_index.await_count == 2
    ttl_call, unique_call = mock_collection.create_index.await_args_list
    assert ttl_call.args[0] == "expires_at"
    assert ttl_call.kwargs["expireAfterSeconds"] == 0
    assert unique_call.args[0] == [("tenant_id", 1), ("account_id", 1)]
    assert unique_call.kwargs["unique"] is True


# ---------------------------------------------------------------------------
# Lock acquire/release — time is frozen, never slept
# ---------------------------------------------------------------------------


@patch("services.scheduler.datetime")
def test_acquire_lock_records_ttl_expiry_from_frozen_time(mock_datetime):
    frozen_now = datetime(2026, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
    mock_datetime.now.return_value = frozen_now

    mock_db, mock_collection = _mock_db()

    acquired = asyncio.run(scheduler._acquire_lock(mock_db, "demo-tenant", "acct-1"))

    assert acquired is True
    mock_collection.insert_one.assert_awaited_once()
    doc = mock_collection.insert_one.await_args.args[0]
    assert doc["tenant_id"] == "demo-tenant"
    assert doc["account_id"] == "acct-1"
    assert doc["acquired_at"] == frozen_now
    assert doc["expires_at"] == frozen_now + timedelta(seconds=scheduler.LOCK_TTL_SECONDS)


def test_acquire_lock_returns_false_on_duplicate_key():
    mock_db, mock_collection = _mock_db()
    mock_collection.insert_one.side_effect = Exception("E11000 duplicate key error")

    acquired = asyncio.run(scheduler._acquire_lock(mock_db, "demo-tenant", "acct-1"))

    assert acquired is False


def test_release_lock_deletes_the_lock_document():
    mock_db, mock_collection = _mock_db()

    asyncio.run(scheduler._release_lock(mock_db, "demo-tenant", "acct-1"))

    mock_collection.delete_one.assert_awaited_once_with({"tenant_id": "demo-tenant", "account_id": "acct-1"})


# ---------------------------------------------------------------------------
# Overlap guard: a locked account is skipped, not re-run
# ---------------------------------------------------------------------------


@patch("services.scheduler.run_pipeline_for_account", new_callable=AsyncMock)
@patch("services.scheduler._release_lock", new_callable=AsyncMock)
@patch("services.scheduler._acquire_lock", new_callable=AsyncMock)
@patch("services.scheduler._connected_accounts", new_callable=AsyncMock)
@patch("services.scheduler.get_db")
def test_overlap_guard_skips_account_whose_previous_run_is_in_progress(
    mock_get_db, mock_connected_accounts, mock_acquire_lock, mock_release_lock, mock_run_pipeline
):
    mock_db, _ = _mock_db()
    mock_get_db.return_value = mock_db
    mock_connected_accounts.return_value = [
        {"tenant_id": "demo-tenant", "provider": "aws", "account_id": "acct-locked", "region": "ap-south-1"},
        {"tenant_id": "demo-tenant", "provider": "aws", "account_id": "acct-free", "region": "ap-south-1"},
    ]

    # acct-locked: a previous run is still in progress -> lock not acquired.
    # acct-free: no previous run -> lock acquired.
    async def fake_acquire(db, tenant_id, account_id):
        return account_id != "acct-locked"

    mock_acquire_lock.side_effect = fake_acquire

    asyncio.run(scheduler.run_all_connected_accounts())

    # Only the free account's pipeline ran — the locked one was skipped
    # entirely, not queued or retried.
    mock_run_pipeline.assert_awaited_once_with("demo-tenant", "aws", "acct-free", "ap-south-1")

    # The lock is released only for the account whose pipeline actually ran.
    mock_release_lock.assert_awaited_once_with(mock_db, "demo-tenant", "acct-free")


@patch("services.scheduler.run_pipeline_for_account", new_callable=AsyncMock)
@patch("services.scheduler._release_lock", new_callable=AsyncMock)
@patch("services.scheduler._acquire_lock", new_callable=AsyncMock, return_value=True)
@patch("services.scheduler._connected_accounts", new_callable=AsyncMock, return_value=[])
@patch("services.scheduler.get_db")
def test_no_connected_accounts_falls_back_to_demo_tenant(
    mock_get_db, mock_connected_accounts, mock_acquire_lock, mock_release_lock, mock_run_pipeline
):
    mock_db, _ = _mock_db()
    mock_get_db.return_value = mock_db

    asyncio.run(scheduler.run_all_connected_accounts())

    # Both AWS and Azure demo entries run, so the multi-cloud story demos
    # even before anyone has clicked through onboarding.
    assert mock_run_pipeline.await_count == 2
    calls = [call.args for call in mock_run_pipeline.await_args_list]
    providers = {c[1] for c in calls}
    assert providers == {"aws", "azure"}
    for tenant_id, _provider, _account_id, _region in calls:
        assert tenant_id == "demo-tenant"


@patch("services.scheduler.run_pipeline_for_account", new_callable=AsyncMock)
@patch("services.scheduler._release_lock", new_callable=AsyncMock)
@patch("services.scheduler._acquire_lock", new_callable=AsyncMock, return_value=True)
@patch("services.scheduler._connected_accounts", new_callable=AsyncMock)
@patch("services.scheduler.get_db")
def test_lock_is_released_even_when_pipeline_raises(
    mock_get_db, mock_connected_accounts, mock_acquire_lock, mock_release_lock, mock_run_pipeline
):
    mock_db, _ = _mock_db()
    mock_get_db.return_value = mock_db
    mock_connected_accounts.return_value = [
        {"tenant_id": "demo-tenant", "account_id": "acct-1", "region": "ap-south-1"}
    ]
    mock_run_pipeline.side_effect = RuntimeError("boom")

    # Must not raise out of run_all_connected_accounts — a crashed account
    # shouldn't take the whole scheduler job down with it.
    asyncio.run(scheduler.run_all_connected_accounts())

    mock_release_lock.assert_awaited_once_with(mock_db, "demo-tenant", "acct-1")


# ---------------------------------------------------------------------------
# Supervisor step: moved to services/supervisor/service.py in Phase 4 —
# see tests/unit/test_supervisor_service.py.
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# start_scheduler / shutdown_scheduler
# ---------------------------------------------------------------------------


@patch("services.scheduler.get_settings")
def test_start_scheduler_noop_when_disabled(mock_get_settings):
    mock_get_settings.return_value = MagicMock(scheduler_enabled=False, scheduler_interval_minutes=60)

    result = scheduler.start_scheduler()

    assert result is None


@patch("services.scheduler.get_settings")
def test_start_scheduler_adds_interval_job_then_shuts_down(mock_get_settings):
    mock_get_settings.return_value = MagicMock(scheduler_enabled=True, scheduler_interval_minutes=60)

    # AsyncIOScheduler.start() binds to the running event loop (it's always
    # called from FastAPI's async lifespan in real usage) — needs one here too.
    async def _run():
        started = scheduler.start_scheduler()
        try:
            assert started is not None
            job = started.get_job(scheduler.JOB_ID)
            assert job is not None
            assert job.trigger.interval == timedelta(minutes=60)
        finally:
            scheduler.shutdown_scheduler()

    asyncio.run(_run())
