from datetime import datetime, timezone
from decimal import Decimal
from uuid import UUID, uuid4

from fastapi import APIRouter, HTTPException, Depends

from apps.api.db import get_db
from apps.api.dependencies import CurrentUser
from packages.schemas.schemas import ActionProposal

router = APIRouter(prefix="/v1/recommendations", tags=["recommendations"])

from services.executor.execution_audit import InMemoryExecutionAuditRepository  # noqa: E402
_EXECUTION_AUDIT_REPO = InMemoryExecutionAuditRepository()

_PROPOSALS: dict = {}
_SEED_PROPOSALS: list[ActionProposal] = [
    ActionProposal(
        proposal_id=uuid4(),
        resource_arn="arn:aws:ec2:ap-south-1:demo:instance/i-0912ab3c4d5e6f701",
        action_type="stop_instance",
        template_id="ec2.stop.v1",
        parameters={"instance_id": "i-0912ab3c4d5e6f701", "region": "ap-south-1"},
        expected_monthly_savings=Decimal("14.20"),
        risk_level="low",
        confidence=0.92,
        requires_human_approval=False,
        status="executed",
    ),
    ActionProposal(
        proposal_id=uuid4(),
        resource_arn="arn:aws:ec2:ap-south-1:demo:instance/i-0455cd8e9f0a1b234",
        action_type="resize_instance",
        template_id="ec2.resize.v1",
        parameters={"instance_id": "i-0455cd8e9f0a1b234", "region": "ap-south-1", "target_type": "t3.medium"},
        expected_monthly_savings=Decimal("22.00"),
        risk_level="medium",
        confidence=0.74,
        requires_human_approval=True,
        status="proposed",
    ),
]


def _to_doc(proposal: ActionProposal) -> dict:
    doc = proposal.model_dump()
    doc["proposal_id"] = str(doc["proposal_id"])
    doc["expected_monthly_savings"] = float(doc["expected_monthly_savings"])
    return doc


def _from_doc(doc: dict) -> ActionProposal:
    doc = dict(doc)
    doc.pop("_id", None)
    doc["expected_monthly_savings"] = Decimal(str(doc["expected_monthly_savings"]))
    return ActionProposal(**doc)


async def _proposals_collection():
    db = get_db()
    if await db.proposals.count_documents({}) == 0:
        await db.proposals.insert_many([_to_doc(p) for p in _SEED_PROPOSALS])
    return db.proposals


@router.get("", response_model=list[ActionProposal])
async def list_recommendations(
    current_user: CurrentUser,
    status: str | None = None,
    risk_level: str | None = None,
) -> list[ActionProposal]:
    collection = await _proposals_collection()

    query: dict = {"tenant_id": current_user["tenant_id"]}
    if status:
        query["status"] = status
    if risk_level:
        query["risk_level"] = risk_level

    docs = await collection.find(query).to_list(length=None)
    return [_from_doc(doc) for doc in docs]


@router.post("/{proposal_id}/approve", response_model=ActionProposal)
async def approve_recommendation(proposal_id: UUID, current_user: CurrentUser) -> ActionProposal:
    from packages.schemas.policy import ActionProposal as PolicyProposal
    from services.policy import engine
    from services.policy.policy_adapter import PolicyAdapter

    collection = await _proposals_collection()
    doc = await collection.find_one({"proposal_id": str(proposal_id), "tenant_id": current_user["tenant_id"]})
    if not doc:
        raise HTTPException(status_code=404, detail="Proposal not found")

    env_long = doc.get("environment", "unknown")
    env_short = {"development": "dev", "staging": "staging", "production": "prod"}.get(env_long, "unknown")

    def evaluate_fn(proposal_dict: dict) -> dict:
        result = engine.evaluate(
            environment=env_short,
            risk_level=proposal_dict["risk_level"],
            template_id=proposal_dict["action_template"],
            has_owner_tag=True,
            is_protected=False,
        )
        return {
            "allowed": result.approved,
            "requires_human_review": result.requires_human_approval,
            "reason_codes": [result.reason],
            "policy_version": "engine-v1",
        }

    adapter = PolicyAdapter(evaluator=evaluate_fn, execution_enabled=True, execution_mode="simulation")

    policy_proposal = PolicyProposal(
        proposal_id=str(proposal_id),
        tenant_id=current_user["tenant_id"],
        snapshot_id=doc.get("resource_arn", "unknown"),
        resource_id=doc["parameters"].get("instance_id", "unknown"),
        resource_type="ec2_instance",
        action_template=doc["template_id"],
        environment=env_long if env_long in ("development", "staging", "production") else "unknown",
        risk_level=doc["risk_level"] if doc["risk_level"] in ("low", "medium", "high") else "high",
        rationale=doc.get("rationale", ""),
        parameters=doc.get("parameters", {}),
        estimated_monthly_savings_usd=Decimal(str(doc["expected_monthly_savings"])),
    )
    decision = adapter.evaluate(policy_proposal)

    new_status = "approved" if decision.outcome == "auto_approved" else (
        "proposed" if decision.outcome == "human_review" else "rejected"
    )
    update_fields: dict = {
        "status": new_status,
        "supervisor_outcome": decision.outcome,
        "supervisor_reason_codes": decision.reason_codes,
    }
    if new_status == "rejected":
        # The Monitor agent resurfaces this after an hour if the resource
        # is still present — see apps/api/routers/observation.py.
        update_fields["rejected_at"] = datetime.now(timezone.utc)
    await collection.update_one(
        {"proposal_id": str(proposal_id)},
        {"$set": update_fields},
    )
    doc["status"] = new_status
    return _from_doc(doc)


@router.post("/{proposal_id}/execute", response_model=ActionProposal)
async def execute_recommendation(proposal_id: UUID, current_user: CurrentUser) -> ActionProposal:
    from packages.schemas.policy import ActionProposal as PolicyProposal, PolicyDecision
    from services.executor.simulated_executor import SimulatedExecutor

    collection = await _proposals_collection()
    doc = await collection.find_one({"proposal_id": str(proposal_id), "tenant_id": current_user["tenant_id"]})
    if not doc:
        raise HTTPException(status_code=404, detail="Proposal not found")

    if doc.get("status") in ("executed", "verified"):
        return _from_doc(doc)

    if doc["status"] != "approved" and doc["requires_human_approval"]:
        raise HTTPException(status_code=400, detail="Proposal requires approval before execution")

    env_long = doc.get("environment", "unknown")
    policy_proposal = PolicyProposal(
        proposal_id=str(proposal_id),
        tenant_id=current_user["tenant_id"],
        snapshot_id=doc.get("resource_arn", "unknown"),
        resource_id=doc["parameters"].get("instance_id", "unknown"),
        resource_type="ec2_instance",
        action_template=doc["template_id"],
        environment=env_long if env_long in ("development", "staging", "production") else "unknown",
        risk_level=doc["risk_level"] if doc["risk_level"] in ("low", "medium", "high") else "high",
        provider=doc.get("provider", "aws"),
        rationale=doc.get("rationale", ""),
        parameters=doc.get("parameters", {}),
        # VPS proposals are always savings_type="reclaimable_capacity" with
        # expected_monthly_savings == 0 (packages/schemas/schemas.py), so
        # this Decimal(...) is always a real dollar figure for anything
        # that reaches the executor at all.
        estimated_monthly_savings_usd=Decimal(str(doc["expected_monthly_savings"])),
    )
    decision = PolicyDecision(
        proposal_id=str(proposal_id),
        outcome="auto_approved" if doc["status"] == "approved" else "human_review",
        reason_codes=doc.get("supervisor_reason_codes", []),
        policy_version="engine-v1",
        simulation_allowed=True,
        live_execution_allowed=False,
    )

    executor = SimulatedExecutor(
        audit_repository=_EXECUTION_AUDIT_REPO, execution_enabled=True, execution_mode="simulation"
    )
    record = executor.execute(policy_proposal, decision)

    new_status = "executed" if record.status == "simulated" else doc["status"]
    await collection.update_one(
        {"proposal_id": str(proposal_id)},
        {"$set": {
            "status": new_status,
            "execution_status": record.status,
            "execution_reason_codes": record.reason_codes,
            "execution_would_execute": record.would_execute,
        }},
    )
    doc["status"] = new_status
    return _from_doc(doc)