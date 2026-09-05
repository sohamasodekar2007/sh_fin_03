"""
Analyzer Agent (Detect) Router — Runs rule engine over FOCUS + resource_metrics
to produce findings. Falls back to the legacy CloudSnapshot bundle
(services/analyzer/service.py's backward-compat path) if no FOCUS dataset
has been collected yet for this tenant/provider/account.
"""

from datetime import datetime, timezone
from typing import Any
from uuid import uuid4
from fastapi import APIRouter, Depends, HTTPException, Query

from apps.api.config import get_settings
from apps.api.db import get_db
from apps.api.dependencies import get_current_user
from packages.schemas.cloud_snapshot import CloudSnapshot
from services.agent_log import log_agent_run
from services.analyzer.service import analyze_observation
from services.collector.mock_provider import generate_mock_observation_bundle
from services.focus import repository as focus_repository
from services.focus.metrics import list_resource_metrics

router = APIRouter(prefix="/v1/agent/analyze", tags=["analyzer-agent-detect"])

_CONFIG_RULE_PREFIXES = ("rds.", "dynamodb.", "lambda.", "sg.")


def _default_account_id(settings, provider: str) -> str:
    if provider == "aws":
        return settings.aws_account_id
    if provider == "azure":
        return settings.azure_subscription_id
    if provider == "vps":
        return settings.vps_host
    return ""


@router.post("", response_model=dict[str, Any])
async def trigger_analyzer_agent(
    provider: str | None = Query(default=None),
    account_id: str | None = Query(default=None),
    region: str | None = Query(default=None),
    run_id: str | None = Query(default=None),
    current_user: dict = Depends(get_current_user),
) -> dict[str, Any]:
    """
    Trigger the Analyzer Agent (Detect) to apply deterministic detection rules
    (idle, over-provisioned, unattached storage, non-prod schedule, spend
    anomaly) against the Monitor Agent's FOCUS dataset + resource_metrics
    for `provider` ("aws" | "azure" | "vps", default "aws").
    """
    settings = get_settings()
    provider = (provider or "aws").strip().lower()
    account_id = account_id or _default_account_id(settings, provider)
    region = region or settings.aws_region
    db = get_db()
    tenant_id = current_user.get("tenant_id", "demo-tenant")
    run_id = run_id or str(uuid4())
    started_at = datetime.now(timezone.utc)

    try:
        # 1. Fetch the latest FOCUS dataset the Monitor agent produced for
        #    this tenant/provider/account.
        focus_dataset_id: str | None = None
        dataset = await focus_repository.get_latest_dataset(db, tenant_id, provider, account_id)

        if dataset is not None:
            resource_metrics = await list_resource_metrics(db, tenant_id)
            findings = analyze_observation(dataset, resource_metrics)
            focus_dataset_id = dataset.dataset_id
            snapshot_doc = await db.cloud_snapshots.find_one({"account_id": account_id, "region": region}, {"_id": 0})
            if snapshot_doc and snapshot_doc.get("resources"):
                existing = {(f.get("resource_id"), f.get("rule_id")) for f in findings}
                for finding in analyze_observation(snapshot_doc):
                    key = (finding.get("resource_id"), finding.get("rule_id"))
                    if key not in existing and str(finding.get("rule_id", "")).startswith(_CONFIG_RULE_PREFIXES):
                        findings.append(finding)
                        existing.add(key)
        else:
            # No FOCUS dataset collected yet for this account — fall back
            # to the legacy CloudSnapshot bundle (analyze_observation's
            # backward-compat path converts it through the AWS mapper).
            doc = await db.cloud_snapshots.find_one({"account_id": account_id, "region": region}, {"_id": 0})
            if not doc or not doc.get("resources"):
                doc = await db.cloud_snapshots.find_one({"resource_count": {"$gt": 0}}, {"_id": 0})
            if not doc or not doc.get("resources"):
                snapshot = generate_mock_observation_bundle(account_id=account_id, region=region)
                doc = snapshot.model_dump(mode="json")
            findings = analyze_observation(doc)

        # 2. Store findings in MongoDB collection `analyzer_findings`
        result_payload = {
            "status": "success",
            "agent": "Analyzer Agent (Detect)",
            "run_id": run_id,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "provider": provider,
            "account_id": account_id,
            "region": region,
            "focus_dataset_id": focus_dataset_id,
            "findings_count": len(findings),
            "findings": findings,
            "summary": {
                "idle_ec2_findings": sum(1 for f in findings if f.get("rule_id") == "ec2.idle.v1"),
                "overprovisioned_findings": sum(1 for f in findings if f.get("rule_id") == "ec2.overprovisioned.v1"),
                "unattached_ebs_findings": sum(1 for f in findings if f.get("rule_id") == "ebs.unattached.v1"),
                "nonprod_schedule_findings": sum(1 for f in findings if f.get("rule_id") == "ec2.nonprod_schedule.v1"),
                "spend_anomaly_findings": sum(1 for f in findings if f.get("rule_id") == "cost.anomaly.v1"),
                "rds_findings": sum(1 for f in findings if str(f.get("rule_id", "")).startswith("rds.")),
                "dynamodb_findings": sum(1 for f in findings if str(f.get("rule_id", "")).startswith("dynamodb.")),
                "lambda_findings": sum(1 for f in findings if str(f.get("rule_id", "")).startswith("lambda.")),
                "security_group_findings": sum(1 for f in findings if str(f.get("rule_id", "")).startswith("sg.")),
            }
        }

        try:
            await db.analyzer_findings.update_one(
                {"account_id": account_id, "region": region},
                {"$set": result_payload},
                upsert=True
            )
        except Exception as err:
            print(f"[Analyzer Agent] DB save warning: {err}")

        finished_at = datetime.now(timezone.utc)
        await log_agent_run(
            tenant_id=tenant_id,
            run_id=run_id,
            agent="Analyzer",
            status="success",
            started_at=started_at,
            finished_at=finished_at,
            input_summary={"provider": provider, "account_id": account_id, "region": region},
            output_summary={
                "message": f"[{provider}] Found {len(findings)} findings across compute, storage, database, serverless, network, and spend rules",
                **result_payload["summary"],
            },
            payload=result_payload,
            error=None,
        )

        return result_payload

    except Exception as exc:
        finished_at = datetime.now(timezone.utc)
        try:
            await log_agent_run(
                tenant_id=tenant_id,
                run_id=run_id,
                agent="Analyzer",
                status="failed",
                started_at=started_at,
                finished_at=finished_at,
                input_summary={"provider": provider, "account_id": account_id, "region": region},
                output_summary={"message": f"Analyzer run failed: {exc}"},
                payload={},
                error=str(exc),
            )
        except Exception as log_err:
            print(f"[Analyzer Agent] agent_log warning: {log_err}")
        raise


@router.get("/latest", response_model=dict[str, Any])
async def get_latest_findings(
    account_id: str | None = Query(default=None),
    region: str | None = Query(default=None),
    current_user: dict = Depends(get_current_user),
) -> dict[str, Any]:
    """Retrieve the latest cached findings bundle produced by the Analyzer Agent."""
    settings = get_settings()
    account_id = account_id or settings.aws_account_id
    region = region or settings.aws_region
    db = get_db()
    doc = await db.analyzer_findings.find_one({"account_id": account_id, "region": region}, {"_id": 0})

    if not doc:
        # Generate findings dynamically on the fly
        snapshot = generate_mock_observation_bundle(account_id=account_id, region=region)
        findings = analyze_observation(snapshot.model_dump(mode="json"))
        doc = {
            "status": "success",
            "agent": "Analyzer Agent (Detect)",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "findings_count": len(findings),
            "findings": findings,
        }

    return doc
