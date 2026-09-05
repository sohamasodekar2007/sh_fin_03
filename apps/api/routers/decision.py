"""
Decision Agent (Plan) Router — Turns Analyzer findings into prioritized,
schema-valid ActionProposals. See services/decision/service.py for the
deterministic scoring logic (blueprint 5.3, 6.2).
"""

from datetime import datetime, timezone
from typing import Any
from uuid import uuid4
from fastapi import APIRouter, BackgroundTasks, Depends, Query

from apps.api.config import get_settings
from apps.api.db import get_db
from apps.api.dependencies import get_current_user
from services.agent_log import log_agent_run
from services.analyzer.service import analyze_observation
from services.collector.mock_provider import generate_mock_observation_bundle
from services.decision.service import build_proposals, enrich_proposals_with_llm
from services.supervisor.service import run_supervisor_step

router = APIRouter(prefix="/v1/agent/decide", tags=["decision-agent-plan"])

_ENV_SHORT_TO_LONG = {
    "dev": "development", "development": "development",
    "stage": "staging", "stg": "staging", "staging": "staging",
    "prod": "production", "production": "production",
}

@router.post("", response_model=dict[str, Any])
async def trigger_decision_agent(
    account_id: str | None = Query(default=None),
    region: str | None = Query(default=None),
    run_id: str | None = Query(default=None),
    use_llm: bool = Query(default=True),
    background_tasks: BackgroundTasks = None,
    current_user: dict = Depends(get_current_user),
) -> dict[str, Any]:
    settings = get_settings()
    account_id = account_id or settings.aws_account_id
    region = region or settings.aws_region
    db = get_db()
    tenant_id = current_user.get("tenant_id", "demo-tenant")
    run_id = run_id or str(uuid4())
    started_at = datetime.now(timezone.utc)

    try:
        obs_doc = await db.cloud_snapshots.find_one({"account_id": account_id, "region": region}, {"_id": 0})
        if not obs_doc or not obs_doc.get("resources"):
            snapshot = generate_mock_observation_bundle(account_id=account_id, region=region)
            obs_doc = snapshot.model_dump(mode="json")

        findings_doc = await db.analyzer_findings.find_one({"account_id": account_id, "region": region}, {"_id": 0})
        findings = findings_doc.get("findings") if findings_doc else None
        if not findings:
            findings = analyze_observation(obs_doc)

        proposals = build_proposals(obs_doc, findings)

        # Phase 15 superseded Phase 14's original design here: ASG
        # membership / load-balancer targeting / termination protection
        # used to be checked live, right here, filtering out unsafe stop
        # proposals AFTER build_proposals() already created them. That's
        # now decided once, deterministically, INSIDE build_proposals()
        # itself, from dependency_context attached at collection time
        # (services/collector/ec2_collector.py) — an ASG-managed or
        # termination-protected instance never gets a stop_instance
        # proposal built in the first place (see build_proposals()'s
        # dependency-context branch), so there's nothing left to filter
        # out here. What's left is EBS-cost-split / EIP-note evidence
        # enrichment for stop_instance proposals — unrelated to that
        # decision, still adds real value. Guarded so a missing package
        # (folder deleted) or the flag being off just means no extra
        # evidence gets appended, never a crash.
        if settings.ec2_safety_checks_enabled:
            try:
                from packages.aws.session import AWSClientFactory
                from services.phase14.ec2_safety import attached_ebs_monthly_cost, attached_elastic_ip_note

                factory = AWSClientFactory(settings)
                ec2_client = factory.client("ec2", region_name=region)

                for p in proposals:
                    if p.get("action_type") != "stop_instance":
                        continue
                    instance_id = (p.get("parameters") or {}).get("instance_id")
                    if not instance_id:
                        continue
                    ebs_cost = attached_ebs_monthly_cost(ec2_client, instance_id, cost_by_resource={})
                    eip_note = attached_elastic_ip_note(ec2_client, instance_id)
                    extra = []
                    if ebs_cost is not None:
                        extra.append(f"Attached EBS volumes cost an additional ${ebs_cost:.2f}/mo.")
                    if eip_note:
                        extra.append(eip_note)
                    if extra:
                        p["rationale"] = p.get("rationale", "") + " " + " ".join(extra)
            except Exception as err:
                print(f"[Decision Agent] Phase 14/15 EC2 evidence enrichment warning: {err}")

        # Every trigger (manual, or the hourly scheduler) re-runs Analyzer
        # against the same still-idle resource and rebuilds the same
        # proposal from scratch — without this check, a resource nobody has
        # acted on yet accumulates a fresh duplicate proposal every single
        # run, forever. Skip building a new one when an OPEN (not yet
        # decided) proposal already exists for this exact (resource_arn,
        # action_type); a rejected proposal's own cooldown/resurface logic
        # (apps/api/routers/observation.py's _resurface_rejected_proposals)
        # already handles bringing it back later, so it's excluded here.
        open_docs = await db.proposals.find(
            {"tenant_id": tenant_id, "status": {"$in": ["proposed", "pending_approval"]}},
            {"_id": 0, "resource_arn": 1, "action_type": 1},
        ).to_list(length=None)
        already_open = {(d["resource_arn"], d["action_type"]) for d in open_docs}
        proposals = [p for p in proposals if (p["resource_arn"], p["action_type"]) not in already_open]

        resource_env_by_id: dict[str, str] = {}
        focus_context: dict[str, dict[str, Any]] = {}
        for r in obs_doc.get("resources", []):
            rid = r.get("instance_id") or r.get("resource_id") or r.get("id")
            if rid:
                resource_env_by_id[rid] = str(r.get("environment", "dev")).lower()
                focus_context[rid] = {
                    "resource_name": r.get("resource_name") or r.get("name") or rid,
                    "tags": r.get("tags") or {},
                    "dependency_context": r.get("dependency_context") or {},
                }

        llm_used = False
        if use_llm:
            proposals, llm_used = await enrich_proposals_with_llm(proposals, findings, focus_context)

        result_payload = {
            "status": "success",
            "agent": "Decision Agent (Plan)",
            "run_id": run_id,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "account_id": account_id,
            "region": region,
            "proposals_count": len(proposals),
            "proposals": proposals,
            "llm_used": llm_used,
            "llm_model": settings.openai_model,
            "summary": {
                "auto_executable": sum(1 for p in proposals if not p["requires_human_approval"]),
                "requires_human_approval": sum(1 for p in proposals if p["requires_human_approval"]),
                "total_potential_monthly_savings": round(
                    sum(float(p["expected_monthly_savings"]) for p in proposals), 2
                ),
            },
        }

        try:
            await db.decision_proposals.update_one(
                {"account_id": account_id, "region": region},
                {"$set": result_payload},
                upsert=True,
            )
        except Exception as err:
            print(f"[Decision Agent] DB save warning: {err}")

        try:
            docs = []
            for p in proposals:
                params = p.get("parameters") or {}
                resource_id = params.get("instance_id") or params.get("volume_id") or params.get("resource_id") or ""
                env_short = resource_env_by_id.get(resource_id, "dev")
                docs.append({
                    "proposal_id": p["proposal_id"],
                    "tenant_id": tenant_id,
                    "created_at": started_at,
                    "resource_arn": p["resource_arn"],
                    "resource_id": p.get("resource_id") or resource_id,
                    "resource_name": p.get("resource_name") or focus_context.get(resource_id, {}).get("resource_name") or resource_id,
                    "resource_type": p.get("resource_type"),
                    "tags": p.get("tags") or focus_context.get(resource_id, {}).get("tags") or {},
                    "action_type": p["action_type"],
                    "template_id": p["template_id"],
                    "parameters": p["parameters"],
                    "expected_monthly_savings": p["expected_monthly_savings"],
                    "risk_level": p["risk_level"],
                    "confidence": p["confidence"],
                    "evidence": p["evidence"],
                    "rollback_plan": p["rollback_plan"],
                    "dependency_facts": p.get("dependency_facts") or [],
                    "requires_human_approval": p["requires_human_approval"],
                    "status": "proposed",
                    "environment": _ENV_SHORT_TO_LONG.get(env_short, "unknown"),
                    "rationale": p.get("rationale", ""),
                    "rationale_plain_english": p.get("rationale_plain_english"),
                    "business_impact": p.get("business_impact"),
                    "risk_notes": p.get("risk_notes"),
                })
            if docs:
                await db.proposals.insert_many(docs)
        except Exception as err:
            print(f"[Decision Agent] proposals-collection sync warning: {err}")

        finished_at = datetime.now(timezone.utc)
        await log_agent_run(
            tenant_id=tenant_id,
            run_id=run_id,
            agent="Decision",
            status="success",
            started_at=started_at,
            finished_at=finished_at,
            input_summary={"account_id": account_id, "region": region, "findings_count": len(findings)},
            output_summary={
                "message": f"Built {len(proposals)} proposals, {result_payload['summary']['requires_human_approval']} need approval",
                **result_payload["summary"],
            },
            payload=result_payload,
            error=None,
        )

        # No human in the loop: Decision hands off to the Supervisor directly,
        # right after persisting proposals and logging its own agent run —
        # the scheduler's hourly pipeline relies on this (it reads the
        # result back out of decision_result["supervisor"] rather than
        # invoking the Supervisor step itself; see services/scheduler.py).
        try:
            result_payload["supervisor"] = await run_supervisor_step(
                db, tenant_id, run_id, account_id, region, result_payload, background_tasks=background_tasks
            )
        except Exception as err:
            print(f"[Decision Agent] Supervisor handoff warning: {err}")
            result_payload["supervisor"] = None

        return result_payload

    except Exception as exc:
        finished_at = datetime.now(timezone.utc)
        try:
            await log_agent_run(
                tenant_id=tenant_id,
                run_id=run_id,
                agent="Decision",
                status="failed",
                started_at=started_at,
                finished_at=finished_at,
                input_summary={"account_id": account_id, "region": region},
                output_summary={"message": f"Decision run failed: {exc}"},
                payload={},
                error=str(exc),
            )
        except Exception as log_err:
            print(f"[Decision Agent] agent_log warning: {log_err}")
        raise


@router.get("/latest", response_model=dict[str, Any])
async def get_latest_proposals(
    account_id: str | None = Query(default=None),
    region: str | None = Query(default=None),
    current_user: dict = Depends(get_current_user),
) -> dict[str, Any]:
    settings = get_settings()
    account_id = account_id or settings.aws_account_id
    region = region or settings.aws_region
    db = get_db()
    doc = await db.decision_proposals.find_one({"account_id": account_id, "region": region}, {"_id": 0})

    if not doc:
        snapshot = generate_mock_observation_bundle(account_id=account_id, region=region)
        obs_doc = snapshot.model_dump(mode="json")
        findings = analyze_observation(obs_doc)
        proposals = build_proposals(obs_doc, findings)
        doc = {
            "status": "success",
            "agent": "Decision Agent (Plan)",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "proposals_count": len(proposals),
            "proposals": proposals,
        }

    return doc
