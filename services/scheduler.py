"""
Hourly Monitor -> Analyzer -> Decision -> Supervisor pipeline.

Runs on an APScheduler AsyncIOScheduler, one job per connected cloud
account, every SCHEDULER_INTERVAL_MINUTES (default 60). The chain always
stops after Supervisor — it never calls the executor, regardless of what
the policy engine says about auto-execution. A human approves via
POST /v1/recommendations/{id}/approve before anything can execute.

OVERLAP GUARD: a `scheduler_locks` collection with a TTL index, not an
in-memory flag — a lock document is a unique (tenant_id, account_id) key,
so a second run for the same account fails to insert one (duplicate key)
and is skipped, and a lock left behind by a crashed run expires on its own
via the TTL index rather than wedging that account forever.

SUPERVISOR STEP: apps/api/routers/decision.py invokes it directly (Phase 4
item 4), right after persisting proposals — see
services/supervisor/service.py for the step itself. This module just
carries its result through in run_pipeline_for_account()'s return value.
"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timedelta, timezone
from typing import Any
from uuid import uuid4

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from motor.motor_asyncio import AsyncIOMotorDatabase

from apps.api.config import get_settings
from apps.api.db import get_db

logger = logging.getLogger(__name__)

LOCK_COLLECTION = "scheduler_locks"
# A run should never legitimately take this long — this is a dead-man's
# switch for a crashed run that never reached _release_lock, not the
# expected run duration.
LOCK_TTL_SECONDS = 30 * 60

JOB_ID = "cloudcare_hourly_pipeline"

# Bounds how many (provider, account) pipelines run at once — a slow or
# rate-limited provider must not delay every other account's hourly run,
# but unbounded concurrency could overwhelm Mongo/the cloud APIs.
MAX_CONCURRENT_PIPELINE_RUNS = 4

_scheduler: AsyncIOScheduler | None = None


def _system_user(tenant_id: str) -> dict[str, Any]:
    """A fake `current_user` for calling the agent routers in-process — the
    scheduler is a trusted background job, not an incoming request, so it
    doesn't go through auth."""
    return {"user_id": "scheduler", "tenant_id": tenant_id, "email": None, "full_name": "CloudCare Scheduler"}


async def ensure_lock_index(db: AsyncIOMotorDatabase) -> None:
    await db[LOCK_COLLECTION].create_index("expires_at", expireAfterSeconds=0, name="lock_ttl")
    await db[LOCK_COLLECTION].create_index(
        [("tenant_id", 1), ("account_id", 1)], unique=True, name="tenant_account_unique"
    )


async def _acquire_lock(db: AsyncIOMotorDatabase, tenant_id: str, account_id: str) -> bool:
    """True if the lock was acquired (no run in progress for this account),
    False if a previous run is still holding it."""
    now = datetime.now(timezone.utc)
    try:
        await db[LOCK_COLLECTION].insert_one(
            {
                "tenant_id": tenant_id,
                "account_id": account_id,
                "acquired_at": now,
                "expires_at": now + timedelta(seconds=LOCK_TTL_SECONDS),
            }
        )
        return True
    except Exception:  # noqa: BLE001 - duplicate key = lock already held
        return False


async def _release_lock(db: AsyncIOMotorDatabase, tenant_id: str, account_id: str) -> None:
    await db[LOCK_COLLECTION].delete_one({"tenant_id": tenant_id, "account_id": account_id})


async def run_pipeline_for_account(
    tenant_id: str,
    provider: str,
    account_id: str,
    region: str,
    run_id: str | None = None,
) -> dict[str, Any]:
    """Monitor -> Analyzer -> Decision -> Supervisor for one (provider,
    account), one shared run_id, then stop. Calls the router functions
    directly (in-process, no HTTP round-trip, no auth) rather than making
    the scheduler an HTTP client of its own server.

    Decision now invokes the Supervisor step itself (Phase 4 item 4 —
    services/supervisor/service.py, called directly from
    apps/api/routers/decision.py right after persisting proposals), so its
    result is embedded in decision_result["supervisor"] rather than being
    called again here — calling it twice would double-log the Supervisor's
    agent_runs entry and redundantly re-evaluate the same proposals."""
    # Imported lazily to avoid a circular import at module load time
    # (apps.api.main imports this module to start the scheduler).
    from apps.api.routers import analysis, decision, observation

    run_id = run_id or str(uuid4())
    user = _system_user(tenant_id)

    monitor_result = await observation.trigger_monitor_agent(
        provider=provider, account_id=account_id, region=region, run_id=run_id, current_user=user
    )
    analyzer_result = await analysis.trigger_analyzer_agent(
        provider=provider, account_id=account_id, region=region, run_id=run_id, current_user=user
    )
    decision_result = await decision.trigger_decision_agent(
        account_id=account_id, region=region, run_id=run_id, current_user=user
    )

    return {
        "run_id": run_id,
        "provider": provider,
        "monitor": monitor_result,
        "analyzer": analyzer_result,
        "decision": decision_result,
        "supervisor": decision_result.get("supervisor"),
    }


async def _connected_accounts(db: AsyncIOMotorDatabase) -> list[dict[str, Any]]:
    cursor = db.cloud_accounts.find({"connected": True}, {"_id": 0})
    return await cursor.to_list(length=None)


async def _run_one_account(
    semaphore: asyncio.Semaphore,
    db: AsyncIOMotorDatabase,
    account: dict[str, Any],
    default_region: str,
) -> None:
    tenant_id = account.get("tenant_id", "demo-tenant")
    provider = account.get("provider", "aws")
    account_id = account.get("account_id", "")
    region = account.get("region") or default_region

    async with semaphore:
        acquired = await _acquire_lock(db, tenant_id, account_id)
        if not acquired:
            logger.info(
                "scheduler: skipping %s/%s/%s — previous run still in progress", tenant_id, provider, account_id
            )
            return

        try:
            await run_pipeline_for_account(tenant_id, provider, account_id, region)
        except Exception:
            # One provider failing must never abort the others — asyncio.gather
            # runs every account's coroutine independently, and each agent
            # step (Monitor/Analyzer/Decision/Supervisor) already logs its
            # own "failed" agent_runs entry before re-raising, so the audit
            # trail is complete without an extra log call here.
            logger.exception("scheduler: pipeline failed for %s/%s/%s", tenant_id, provider, account_id)
        finally:
            await _release_lock(db, tenant_id, account_id)


async def run_all_connected_accounts() -> None:
    """The scheduled job body: one pipeline run per connected cloud
    account, fanned out concurrently (bounded by
    MAX_CONCURRENT_PIPELINE_RUNS) rather than one at a time — a slow or
    rate-limited provider must not delay every other account's hourly run.
    Each account is still independently lock-guarded."""
    db = get_db()
    settings = get_settings()
    accounts = await _connected_accounts(db)

    if not accounts:
        # No cloud account has been validated yet — still run once per
        # provider for the demo tenant so the hourly job has something to
        # show, matching the "never show a blank dashboard" pattern used
        # everywhere else in this build (FOCUS sample data, etc). Both AWS
        # and Azure are included so the multi-cloud story demos even before
        # anyone has clicked through onboarding.
        accounts = [
            {
                "tenant_id": "demo-tenant",
                "provider": "aws",
                "account_id": settings.aws_account_id or "demo-account",
                "region": settings.aws_region,
            },
            {
                "tenant_id": "demo-tenant",
                "provider": "azure",
                "account_id": settings.azure_subscription_id or "demo-subscription",
                "region": "global",
            },
        ]
        # VPS only if actually configured — unlike AWS/Azure it has no
        # sample-data fallback to demo with, so an unset VPS_HOST would
        # just add a pointless "not configured" pipeline run every hour.
        if settings.vps_host:
            accounts.append(
                {
                    "tenant_id": "demo-tenant",
                    "provider": "vps",
                    "account_id": settings.vps_host,
                    "region": "on-premises",
                }
            )

    semaphore = asyncio.Semaphore(MAX_CONCURRENT_PIPELINE_RUNS)
    await asyncio.gather(
        *(_run_one_account(semaphore, db, account, settings.aws_region) for account in accounts)
    )


async def refresh_s3_parquet_analysis_job() -> None:
    """Refresh the dashboard-ready Parquet analysis artifact in S3.

    Uses the same hourly cadence as the CloudCare pipeline and only runs
    when FOCUS_EXPORT_S3_BUCKET is configured. Failures are logged so a bad
    export object never prevents the main monitor/analyzer pipeline from
    running on the next tick.
    """
    settings = get_settings()
    if not settings.focus_export_s3_bucket:
        logger.info("scheduler: skipping parquet analysis refresh; FOCUS_EXPORT_S3_BUCKET is not configured")
        return
    try:
        from apps.api.routers.parquet_analysis import refresh_s3_parquet_analysis

        refresh_s3_parquet_analysis()
    except Exception:
        logger.exception("scheduler: S3 parquet analysis refresh failed")


def start_scheduler() -> AsyncIOScheduler | None:
    global _scheduler
    settings = get_settings()

    if not settings.scheduler_enabled:
        logger.info("scheduler: SCHEDULER_ENABLED=false, not starting")
        return None

    _scheduler = AsyncIOScheduler()
    _scheduler.add_job(
        run_all_connected_accounts,
        "interval",
        minutes=settings.scheduler_interval_minutes,
        id=JOB_ID,
        coalesce=True,
        max_instances=1,
        replace_existing=True,
    )
    _scheduler.add_job(
        refresh_s3_parquet_analysis_job,
        "interval",
        minutes=settings.scheduler_interval_minutes,
        id="s3_parquet_analysis_hourly_rewrite",
        coalesce=True,
        max_instances=1,
        replace_existing=True,
    )
    _scheduler.start()
    logger.info("scheduler: started, interval=%d minutes", settings.scheduler_interval_minutes)
    return _scheduler


def shutdown_scheduler() -> None:
    global _scheduler
    if _scheduler is not None:
        _scheduler.shutdown(wait=False)
        _scheduler = None
