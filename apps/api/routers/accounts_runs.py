"""
CloudAccount onboarding (spec section 3, AES-256-GCM at rest) and the main
pipeline trigger — POST /v1/runs is what "Run Monitor Agent Scan" in the
dashboard and the chat orchestrator's trigger_monitor_agent() tool both
call.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel

from apps.api.db import get_db
from apps.api.dependencies import get_current_user
from apps.api.pipeline import run_pipeline
from packages.schemas.schemas import CloudAccount, UserInDB

router = APIRouter(prefix="/v1", tags=["accounts"])


class CloudAccountCreate(BaseModel):
    provider: str
    display_name: str
    account_id: str
    region: str = "us-east-1"
    role_arn: str | None = None
    external_id: str | None = None
    credentials_json: str | None = None  # GCP service-account JSON / Azure client secret / on-prem SSH key


@router.post("/accounts", status_code=status.HTTP_201_CREATED)
async def create_account(payload: CloudAccountCreate, user: UserInDB = Depends(get_current_user)):
    if payload.provider not in ("aws", "gcp", "azure", "onprem"):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Unknown provider.")

    encrypted = None
    if payload.credentials_json:
        from services.adapters.crypto import encrypt_credentials

        encrypted = encrypt_credentials(payload.credentials_json)

    account = CloudAccount(
        tenant_id=user.tenant_id,
        provider=payload.provider,  # type: ignore[arg-type]
        display_name=payload.display_name,
        account_id=payload.account_id,
        region=payload.region,
        role_arn=payload.role_arn,
        external_id=payload.external_id,
        encrypted_credentials=encrypted,
    )

    from services.adapters.base import get_adapter

    adapter = get_adapter(account.provider)
    account.status = "validated" if await adapter.validate_credentials(account) else "pending"

    db = get_db()
    await db.cloud_accounts.insert_one(account.model_dump())
    return account.model_dump()


@router.get("/accounts")
async def list_accounts(user: UserInDB = Depends(get_current_user)):
    db = get_db()
    accounts = await db.cloud_accounts.find({"tenant_id": user.tenant_id}).to_list(length=100)
    for a in accounts:
        a.pop("_id", None)
        a.pop("encrypted_credentials", None)  # never round-trip ciphertext to the client
    return accounts


@router.post("/runs")
async def trigger_run(user: UserInDB = Depends(get_current_user)):
    """Runs the full 6-node LangGraph pipeline (Monitor -> Verifier) for
    this tenant's onboarded CloudAccounts, falling back to one demo account
    per provider when none are onboarded yet."""
    db = get_db()
    raw_accounts = await db.cloud_accounts.find({"tenant_id": user.tenant_id}).to_list(length=100)
    cloud_accounts = [CloudAccount.model_validate({k: v for k, v in a.items() if k != "_id"}) for a in raw_accounts]

    result = await run_pipeline(user.tenant_id, cloud_accounts or None)
    return {
        "run_id": result["run_id"],
        "status": result["status"],
        "summary": {
            "resources_scanned": result.get("observation", {}).get("resources_scanned", 0),
            "findings": len(result.get("findings", [])),
            "proposals": len(result.get("proposals", [])),
            "executed": len(result.get("execution_log", [])),
        },
        "trace": result.get("trace", []),
    }
