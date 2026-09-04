"""
Monitor Agent (Observe) Router — Endpoint for triggering data collection and retrieving observation bundles.
Produces observation.json matching CloudCareState.observation.
"""

from datetime import datetime, timedelta, timezone
from typing import Any
from uuid import uuid4
from fastapi import APIRouter, Depends, HTTPException, Query

from apps.api.config import get_settings
from apps.api.db import get_db
from apps.api.dependencies import get_current_user
from packages.azure.session import AzureClientFactory
from packages.aws.session import AWSClientFactory
from packages.schemas.cloud_snapshot import CloudSnapshot
from packages.schemas.focus import FocusDataset
from services.agent_log import log_agent_run
from services.collector.azure.collector_service import AzureCollectorService
from services.collector.collector_service import AWSCollectorService
from services.collector.mock_provider import generate_mock_observation_bundle
from services.focus import repository as focus_repository
from services.focus.mappers import azure as azure_focus_mapper
from services.focus.mappers.aws import map_snapshot_to_focus
from services.focus.metrics import ResourceMetric, save_resource_metrics
from services.focus.sample_loader import load_sample_dataset

router = APIRouter(prefix="/v1/agent/observe", tags=["monitor-agent-observe"])

# Rejected proposals resurface after this long, per item 5 — see
# _resurface_rejected_proposals() below.
_REJECTION_RESURFACE_AFTER = timedelta(hours=1)


def _dashboard_environment(raw: Any) -> str:
    normalized = str(raw or "").strip().lower()
    if normalized in {"prod", "production"}:
        return "prod"
    if normalized in {"stage", "stg", "staging"}:
        return "staging"
    return "dev"


def _cost_by_resource_id(focus_dataset: FocusDataset | None) -> dict[str, float]:
    """Sums FOCUS BilledCost per ResourceId across a dataset's records —
    the real per-resource cost the Resources page joins against. A
    resource with no matching entry has no observed cost this period; the
    caller must treat a missing key as None, never as 0.0 or a guess."""
    cost_by_resource: dict[str, float] = {}
    if focus_dataset is None:
        return cost_by_resource
    for record in focus_dataset.records:
        if record.ResourceId:
            cost_by_resource[record.ResourceId] = cost_by_resource.get(
                record.ResourceId, 0.0
            ) + float(record.BilledCost)
    return cost_by_resource


def _focus_rows_by_resource_id(focus_dataset: FocusDataset | None) -> dict[str, int]:
    rows_by_resource: dict[str, int] = {}
    if focus_dataset is None:
        return rows_by_resource
    for record in focus_dataset.records:
        if record.ResourceId:
            rows_by_resource[record.ResourceId] = rows_by_resource.get(record.ResourceId, 0) + 1
    return rows_by_resource


def _resource_cost_source(focus_dataset: FocusDataset | None, has_cost_row: bool) -> str:
    if not focus_dataset or not has_cost_row:
        return "no_focus_row"
    return {
        "live_export": "focus_live_export",
        "synthesized": "focus_synthesized",
        "sample": "focus_sample",
        "modelled": "focus_modelled",
    }.get(focus_dataset.source, "no_focus_row")


def _dashboard_status(resource: dict[str, Any], cpu_p95: float) -> str:
    pattern = str(resource.get("tags", {}).get("Pattern", "")).lower()
    if pattern == "idle" or cpu_p95 < 5:
        return "Idle"
    if pattern in {"oversized", "overprovisioned", "over-provisioned"}:
        return "Over-provisioned"
    if resource.get("state") not in {None, "running"}:
        return "At-risk"
    return "Healthy"


def _focus_source_label(focus_source: str) -> str:
    """Collapse FocusDataset's 3-value source ("live_export" | "synthesized"
    | "sample") into the 2-value label the API response promises: any
    provider-derived data is "live", pure FOCUS-Sample-Data fallback is
    "sample"."""
    return "sample" if focus_source == "sample" else "live"


async def _resurface_rejected_proposals(
    db: Any,
    tenant_id: str,
    resources: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """
    A proposal the user rejected more than an hour ago, for a resource that
    is still present in this snapshot, gets a fresh proposal recorded —
    rejecting something once shouldn't silently suppress it forever.
    """
    resource_ids = {
        rid
        for r in resources
        if (rid := r.get("resource_id") or r.get("instance_id"))
    }
    if not resource_ids:
        return []

    cutoff = datetime.now(timezone.utc) - _REJECTION_RESURFACE_AFTER
    cursor = db.proposals.find(
        {"tenant_id": tenant_id, "status": "rejected", "rejected_at": {"$lt": cutoff}}
    )
    stale_rejections = await cursor.to_list(length=None)

    resurfaced_docs: list[dict[str, Any]] = []
    for old_doc in stale_rejections:
        old_resource_id = (old_doc.get("parameters") or {}).get("instance_id")
        if old_resource_id not in resource_ids:
            continue

        new_doc = dict(old_doc)
        new_doc.pop("_id", None)
        old_proposal_id = new_doc.get("proposal_id")
        new_doc["proposal_id"] = str(uuid4())
        new_doc["status"] = "proposed"
        new_doc["supersedes_proposal_id"] = old_proposal_id
        new_doc["rejected_at"] = None
        resurfaced_docs.append(new_doc)

    if resurfaced_docs:
        await db.proposals.insert_many(resurfaced_docs)

    return resurfaced_docs


def _resource_metrics_from_cpu_metrics(snapshot: CloudSnapshot, tenant_id: str) -> list[ResourceMetric]:
    """
    Bridges CloudSnapshot.cpu_metrics (EC2CpuMetric — AWS's own shape) into
    the FOCUS-era `resource_metrics` collection the Analyzer (Phase 3)
    reads. CloudWatchCollector now also collects NetworkIn/NetworkOut (no
    agent required), so network_p95_bytes is real when available. Memory
    stays honestly None — EC2 genuinely has no memory metric without the
    CloudWatch Agent installed on the instance, which this app has no way
    to query — never fabricated, and services/analyzer/service.py treats a
    missing signal as "don't fire on it," not as zero.
    """
    metrics: list[ResourceMetric] = []
    for cpu_metric in snapshot.cpu_metrics:
        cpu_p95 = cpu_metric.maximum_cpu_percent
        cpu_avg = cpu_metric.average_cpu_percent
        if cpu_p95 is None and cpu_avg is None:
            continue
        metrics.append(
            ResourceMetric(
                resource_id=cpu_metric.instance_id,
                tenant_id=tenant_id,
                window_start=cpu_metric.window_start,
                window_end=cpu_metric.window_end,
                cpu_p95=cpu_p95 if cpu_p95 is not None else cpu_avg,
                cpu_avg=cpu_avg if cpu_avg is not None else cpu_p95,
                mem_p95=None,
                network_p95_bytes=cpu_metric.maximum_network_bytes,
                sample_count=cpu_metric.datapoint_count,
            )
        )
    return metrics


async def _collect_aws(
    settings, tenant_id: str, account_id: str, region: str
) -> tuple[CloudSnapshot, list[ResourceMetric]]:
    snapshot: CloudSnapshot | None = None

    if settings.aws_access_key_id or settings.aws_role_arn or settings.aws_profile:
        try:
            factory = AWSClientFactory(settings)
            service = AWSCollectorService(client_factory=factory, region=region, account_id=account_id)
            snapshot = service.collect_snapshot()
            print(f"[Monitor Agent] Live AWS boto3 collection succeeded in {region}! Found {snapshot.resource_count} live resources.")
        except Exception as live_err:
            print(f"[Monitor Agent] Live AWS collection fallback to synthetic data: {live_err}")

    if not snapshot or snapshot.resource_count == 0:
        snapshot = generate_mock_observation_bundle(account_id=account_id, region=region)

    return snapshot, _resource_metrics_from_cpu_metrics(snapshot, tenant_id)


async def _collect_azure(
    settings,
    tenant_id: str,
    subscription_id: str,
) -> tuple[CloudSnapshot, list[ResourceMetric], FocusDataset]:
    """
    Returns (snapshot, metrics, focus_dataset). Tries live Azure collection
    first when AZURE_TENANT_ID/CLIENT_ID/CLIENT_SECRET/SUBSCRIPTION_ID are
    all configured; falls back to FOCUS sample data — same as GCP/VPS —
    whenever Azure isn't connected yet, or the live collection comes back
    with nothing (bad credentials, no role assignment, etc).
    """
    azure_configured = bool(
        settings.azure_tenant_id
        and settings.azure_client_id
        and settings.azure_client_secret
        and subscription_id
    )

    if azure_configured:
        try:
            factory = AzureClientFactory(settings)
            collector_service = AzureCollectorService(
                client_factory=factory, subscription_id=subscription_id, tenant_id=tenant_id
            )
            snapshot, metrics = collector_service.collect_snapshot_and_metrics()

            if snapshot.resource_count > 0:
                focus_dataset = azure_focus_mapper.map_account_to_focus(
                    tenant_id,
                    subscription_id,
                    factory,
                    focus_storage_account=settings.azure_focus_storage_account,
                    focus_container=settings.azure_focus_container,
                )
                if focus_dataset.row_count > 0:
                    print(
                        f"[Monitor Agent] Live Azure collection succeeded! Found "
                        f"{snapshot.resource_count} live resources, {focus_dataset.row_count} FOCUS rows."
                    )
                    return snapshot, metrics, focus_dataset
        except Exception as live_err:
            print(f"[Monitor Agent] Live Azure collection fallback to FOCUS sample data: {live_err}")

    # Not connected, or live collection produced nothing — FOCUS sample
    # data, matching the "never show a blank dashboard" pattern used
    # everywhere else in this build.
    focus_dataset = load_sample_dataset("azure", tenant_id)
    empty_snapshot = CloudSnapshot(
        account_id=subscription_id or "sample-subscription",
        region="global",
        collected_at=datetime.now(timezone.utc),
        status="success",
        resource_count=0,
        metric_count=0,
        cost_day_count=0,
        resources=[],
        cpu_metrics=[],
        daily_costs=[],
        issues=[],
    )
    return empty_snapshot, [], focus_dataset


def _vps_snapshot(host: str, resources: list[Any]) -> CloudSnapshot:
    return CloudSnapshot(
        account_id=host or "vps-not-configured",
        region="on-premises",
        collected_at=datetime.now(timezone.utc),
        status="success",
        resource_count=len(resources),
        metric_count=0,
        cost_day_count=0,
        resources=[
            {**r.model_dump(mode="json"), "instance_type": r.instance_type, "state": r.state} for r in resources
        ],
        cpu_metrics=[],
        daily_costs=[],
        issues=[],
    )


async def _collect_vps(
    db: Any,
    settings,
    tenant_id: str,
) -> tuple[CloudSnapshot, list[ResourceMetric], FocusDataset, str]:
    """
    Returns (snapshot, metrics, focus_dataset, detection_path). VPS has no
    FOCUS sample data to fall back to (services/focus/sample_loader.py has
    no on-premises provider at all), so an unconfigured VPS just returns an
    honest, empty "modelled" dataset rather than pretending to have one.
    """
    if not settings.vps_host:
        empty_snapshot = _vps_snapshot("", [])
        focus_dataset = FocusDataset(
            tenant_id=tenant_id,
            provider="vps",
            account_id="vps-not-configured",
            granularity="daily",
            source="modelled",
            row_count=0,
            records=[],
            warnings=["vps_not_configured"],
        )
        return empty_snapshot, [], focus_dataset, "not_configured"

    from packages.vps.session import VPSConnection, VPSConnectionError
    from services.collector.vps.inventory import collect_vps_inventory
    from services.collector.vps.metrics import backfill_from_sar, sample_live_metrics, sample_prometheus_metrics, sysstat_available
    from services.focus.mappers.vps import map_vps_to_focus

    conn = VPSConnection(
        host=settings.vps_host,
        username=settings.vps_username,
        key_path=settings.vps_ssh_key_path,
        port=settings.vps_port,
        key_passphrase=settings.vps_ssh_key_passphrase,
    )

    try:
        inventory_result = collect_vps_inventory(conn, settings.vps_host)
        resources = inventory_result.resources

        account_doc = await db.cloud_accounts.find_one(
            {"tenant_id": tenant_id, "provider": "vps", "account_id": settings.vps_host}
        ) or {}
        already_backfilled = bool(account_doc.get("vps_sar_backfill_done"))

        metrics: list[ResourceMetric] = []
        history_warm = bool(account_doc.get("vps_history_warm"))

        if settings.vps_metrics_endpoint:
            # Prometheus preferred over SSH when configured — real time
            # series from node_exporter, no per-sample SSH round trip.
            metrics = sample_prometheus_metrics(
                settings.vps_metrics_endpoint, tenant_id, resources, window_days=settings.vps_sar_backfill_days
            )
            history_warm = bool(metrics) and metrics[0].sample_count >= settings.vps_sar_backfill_days
        elif settings.vps_sar_backfill_enabled and not already_backfilled:
            if sysstat_available(conn):
                metrics, days_covered = backfill_from_sar(
                    conn, tenant_id, resources, days=settings.vps_sar_backfill_days
                )
                history_warm = days_covered >= settings.vps_sar_backfill_days
            else:
                history_warm = False
                print(
                    f"[Monitor Agent] VPS sysstat not found on {settings.vps_host} — "
                    "history will warm up over the next 14 hourly runs instead of backfilling."
                )

            await db.cloud_accounts.update_one(
                {"tenant_id": tenant_id, "provider": "vps", "account_id": settings.vps_host},
                {
                    "$set": {
                        "connected": True,
                        "vps_sar_backfill_done": True,
                        "vps_history_warm": history_warm,
                    }
                },
                upsert=True,
            )

        if not metrics:
            metrics = sample_live_metrics(conn, tenant_id, resources)
    except VPSConnectionError as exc:
        print(f"[Monitor Agent] VPS connection failed: {exc}")
        empty_snapshot = _vps_snapshot(settings.vps_host, [])
        focus_dataset = FocusDataset(
            tenant_id=tenant_id,
            provider="vps",
            account_id=settings.vps_host,
            granularity="daily",
            source="modelled",
            row_count=0,
            records=[],
            warnings=[f"vps_connection_failed:{exc}"],
        )
        return empty_snapshot, [], focus_dataset, "connection_failed"
    finally:
        conn.close()

    snapshot = _vps_snapshot(settings.vps_host, resources)
    focus_dataset = map_vps_to_focus(
        {
            "host": settings.vps_host,
            "resources": [r.model_dump(mode="json") for r in resources],
        },
        tenant_id,
        monthly_cost=settings.vps_monthly_cost,
        monthly_cost_currency=settings.vps_monthly_cost_currency,
        usd_to_inr=settings.usd_to_inr,
        company_name=settings.vps_company_name,
    )
    return snapshot, metrics, focus_dataset, inventory_result.detection_path


@router.post("", response_model=dict[str, Any])
async def trigger_monitor_agent(
    provider: str | None = Query(default=None),
    account_id: str | None = Query(default=None),
    region: str | None = Query(default=None),
    run_id: str | None = Query(default=None),
    current_user: dict = Depends(get_current_user),
) -> dict[str, Any]:
    """
    Trigger the Monitor Agent (Observe) for `provider` ("aws" | "azure",
    default "aws"), collecting inventory, telemetry and billing history,
    normalizing them into one observation.json bundle plus a FOCUS 1.0
    dataset. Uses live SDKs if credentials exist; otherwise falls back to
    synthetic/sample data.
    """
    db = get_db()
    settings = get_settings()
    tenant_id = current_user.get("tenant_id", "demo-tenant")
    provider = (provider or "aws").strip().lower()

    run_id = run_id or str(uuid4())
    started_at = datetime.now(timezone.utc)

    if provider not in ("aws", "azure", "vps"):
        raise HTTPException(
            status_code=400, detail=f"Unsupported provider: {provider!r}. Use 'aws', 'azure' or 'vps'."
        )

    if provider == "aws":
        account_id = account_id or settings.aws_account_id
        region = region or settings.aws_region
    elif provider == "azure":
        account_id = account_id or settings.azure_subscription_id
        region = region or "global"
    else:
        account_id = account_id or settings.vps_host
        region = region or "on-premises"

    try:
        metrics: list[ResourceMetric] = []
        focus_dataset: FocusDataset | None = None
        detection_path: str | None = None

        if provider == "aws":
            snapshot, metrics = await _collect_aws(settings, tenant_id, account_id, region)
        elif provider == "azure":
            snapshot, metrics, focus_dataset = await _collect_azure(settings, tenant_id, account_id)
        else:
            snapshot, metrics, focus_dataset, detection_path = await _collect_vps(db, settings, tenant_id)
            account_id = snapshot.account_id

        snapshot_data = snapshot.model_dump(mode="json")

        # 2. Persist in MongoDB collection `cloud_snapshots`
        try:
            await db.cloud_snapshots.update_one(
                {"account_id": account_id, "region": region},
                {"$set": snapshot_data},
                upsert=True
            )
        except Exception as err:
            print(f"[Monitor Agent] DB save warning: {err}")

        # 3. Normalize into FOCUS 1.0 and persist the dataset — moved ahead
        # of the resources-collection sync below so that step can join each
        # resource to its real FOCUS BilledCost instead of a fabricated
        # flat guess.
        focus_dataset_id: str | None = None
        focus_row_count = 0
        focus_source_label = "sample"
        try:
            if focus_dataset is None:
                # AWS path: FOCUS dataset isn't built yet (Azure builds its
                # own inside _collect_azure, since it needs the collectors'
                # per-resource cost data, not just the CloudSnapshot dict).
                focus_dataset = map_snapshot_to_focus(
                    snapshot_data,
                    tenant_id=tenant_id,
                    s3_bucket=settings.focus_export_s3_bucket,
                    s3_prefix=settings.focus_export_s3_prefix,
                    aws_access_key_id=settings.aws_access_key_id,
                    aws_secret_access_key=settings.aws_secret_access_key,
                    aws_region=settings.aws_region,
                    focus_version=settings.focus_version,
                )
            focus_dataset_id = await focus_repository.save_dataset(db, focus_dataset)
            focus_row_count = focus_dataset.row_count
            # VPS's "modelled" source is deliberately NOT collapsed into
            # "live" — that label exists specifically so the UI can tell a
            # modelled cost apart from an observed one (item 4).
            focus_source_label = focus_dataset.source if provider == "vps" else _focus_source_label(focus_dataset.source)
        except Exception as err:
            print(f"[Monitor Agent] FOCUS normalization warning: {err}")

        # 4. Also update MongoDB `resources` for standard queries (the
        # dashboard's Resources page). Cost is real, joined from the FOCUS
        # dataset just built above — None (never a fabricated number) when
        # a resource genuinely has no billed cost yet.
        try:
            if snapshot.resources:
                cpu_by_instance = {
                    metric.instance_id: float(metric.average_cpu_percent or 0.0)
                    for metric in snapshot.cpu_metrics
                }
                cost_by_resource = _cost_by_resource_id(focus_dataset)
                rows_by_resource = _focus_rows_by_resource_id(focus_dataset)

                formatted_resources = []
                for r in snapshot.resources:
                    resource_id = r.get("resource_id") or r.get("instance_id")
                    cpu_p95 = cpu_by_instance.get(resource_id, 0.0)
                    has_cost_row = resource_id in cost_by_resource
                    real_cost = cost_by_resource.get(resource_id)
                    formatted_resources.append({
                        "id": resource_id,
                        "type": r.get("instance_type", "ec2"),
                        "resource_type": r.get("resource_type"),
                        "state": r.get("state"),
                        "cpu_p95": cpu_p95,
                        "status": _dashboard_status(r, cpu_p95),
                        "monthly_cost_usd": real_cost,
                        "cost_source": _resource_cost_source(focus_dataset, has_cost_row),
                        "focus_dataset_id": focus_dataset_id,
                        "focus_version": focus_dataset.focus_version if focus_dataset else settings.focus_version,
                        "focus_source": focus_dataset.source if focus_dataset else None,
                        "focus_row_count": rows_by_resource.get(resource_id, 0),
                        "tenant_id": tenant_id,
                        "environment": _dashboard_environment(r.get("environment")),
                        "tags": r.get("tags", {}),
                    })
                resource_ids = [doc["id"] for doc in formatted_resources if doc.get("id")]
                # Clears every doc this provider previously owned (handles a
                # decommissioned resource dropping out) PLUS any doc sharing
                # one of these ids regardless of its stored provider — some
                # resources.py documents predate the `provider` field and
                # sit there as `provider: null` forever otherwise, since an
                # exact {"provider": provider} match never touches them.
                await db.resources.delete_many({
                    "tenant_id": tenant_id,
                    "$or": [{"provider": provider}, {"id": {"$in": resource_ids}}],
                })
                for doc in formatted_resources:
                    doc["provider"] = provider
                await db.resources.insert_many(formatted_resources)
        except Exception as err:
            print(f"[Monitor Agent] Resource sync warning: {err}")

        # 4b. Persist Azure telemetry directly to `resource_metrics` (Azure
        # only — AWS's cpu_metrics still lives embedded on the snapshot).
        if metrics:
            try:
                await save_resource_metrics(db, metrics)
            except Exception as err:
                print(f"[Monitor Agent] Resource metrics save warning: {err}")

        # 5. Resurface proposals the user rejected more than an hour ago,
        #    for resources still present in this snapshot.
        resurfaced: list[dict[str, Any]] = []
        try:
            resurfaced = await _resurface_rejected_proposals(db, tenant_id, snapshot.resources)
        except Exception as err:
            print(f"[Monitor Agent] Proposal resurfacing warning: {err}")

        # 6. Format observation.json contract payload
        summary = {
            "total_resources": snapshot.resource_count,
            "metrics_collected": snapshot.metric_count,
            "cost_days_collected": snapshot.cost_day_count,
            "idle_instances_detected": sum(1 for r in snapshot.resources if r.get("tags", {}).get("Pattern") == "idle"),
            "oversized_instances_detected": sum(1 for r in snapshot.resources if r.get("tags", {}).get("Pattern") == "oversized"),
            "unattached_ebs_volumes_detected": sum(
                1 for r in snapshot.resources
                if r.get("resource_type") in ("ebs_volume", "azure_disk") and r.get("state") in ("available", "unattached")
            ),
            "proposals_resurfaced": len(resurfaced),
        }

        response = {
            "status": "success",
            "agent": "Monitor Agent (Observe)",
            "run_id": run_id,
            "provider": provider,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "account_id": account_id,
            "region": region,
            "observation": snapshot_data,
            "focus_dataset_id": focus_dataset_id,
            "focus_version": focus_dataset.focus_version if focus_dataset else settings.focus_version,
            "row_count": focus_row_count,
            "resource_count": snapshot.resource_count,
            "source": focus_source_label,
            "detection_path": detection_path,
            "summary": summary,
        }

        finished_at = datetime.now(timezone.utc)
        try:
            await log_agent_run(
                tenant_id=tenant_id,
                run_id=run_id,
                agent="Monitor",
                status="success",
                started_at=started_at,
                finished_at=finished_at,
                input_summary={"provider": provider, "account_id": account_id, "region": region},
                output_summary={
                    "message": (
                        f"[{provider}] Collected {summary['total_resources']} resources, "
                        f"{focus_row_count} FOCUS rows ({focus_source_label})"
                    ),
                    **summary,
                    "focus_dataset_id": focus_dataset_id,
                    "source": focus_source_label,
                },
                payload=response,
                error=None,
            )
        except Exception as err:
            print(f"[Monitor Agent] agent_log warning: {err}")

        return response

    except Exception as exc:
        finished_at = datetime.now(timezone.utc)
        try:
            await log_agent_run(
                tenant_id=tenant_id,
                run_id=run_id,
                agent="Monitor",
                status="failed",
                started_at=started_at,
                finished_at=finished_at,
                input_summary={"provider": provider, "account_id": account_id, "region": region},
                output_summary={"message": f"Monitor run failed: {exc}"},
                payload={},
                error=str(exc),
            )
        except Exception as log_err:
            print(f"[Monitor Agent] agent_log warning: {log_err}")
        raise


@router.get("/latest", response_model=dict[str, Any])
async def get_latest_observation(
    account_id: str | None = Query(default=None),
    region: str | None = Query(default=None),
    current_user: dict = Depends(get_current_user),
) -> dict[str, Any]:
    """Retrieve the latest cached observation.json bundle produced by the Monitor Agent."""
    db = get_db()
    settings = get_settings()
    account_id = account_id or settings.aws_account_id
    region = region or settings.aws_region
    doc = await db.cloud_snapshots.find_one({"account_id": account_id, "region": region}, {"_id": 0})

    if not doc:
        doc = await db.cloud_snapshots.find_one({"resource_count": {"$gt": 0}}, {"_id": 0})

    if not doc or not doc.get("resources"):
        # Generate default observation bundle
        snapshot: CloudSnapshot = generate_mock_observation_bundle(account_id=account_id, region=region)
        doc = snapshot.model_dump(mode="json")

    resources = doc.get("resources", [])
    return {
        "status": "success",
        "agent": "Monitor Agent (Observe)",
        "observation": doc,
        "summary": {
            "total_resources": doc.get("resource_count", len(resources)),
            "metrics_collected": doc.get("metric_count", 20),
            "cost_days_collected": doc.get("cost_day_count", 30),
            "idle_instances_detected": sum(1 for r in resources if isinstance(r, dict) and r.get("tags", {}).get("Pattern") == "idle"),
            "oversized_instances_detected": sum(1 for r in resources if isinstance(r, dict) and r.get("tags", {}).get("Pattern") == "oversized"),
            "unattached_ebs_volumes_detected": sum(1 for r in resources if isinstance(r, dict) and r.get("resource_type") == "ebs_volume"),
        }
    }
