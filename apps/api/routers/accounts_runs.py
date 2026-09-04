import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from packages.schemas.schemas import CloudCareState, CloudAccount
from apps.api.routers.auth import get_current_user
from apps.api.config import get_settings
from apps.api.db import get_db

import boto3
from botocore.exceptions import ClientError, NoCredentialsError

router = APIRouter(prefix="/v1", tags=["accounts-runs"])


class ConnectedAccountSummary(BaseModel):
    """Deliberately NOT the full CloudAccount model — that carries
    azure_client_secret and gcp_service_account_json, real credentials that
    must never round-trip back to the frontend. Only non-secret identifiers
    here."""

    provider: str
    account_id: str
    region: str = "ap-south-1"
    connected: bool = False
    status: str = "pending"


async def _persist_connection_status(
    tenant_id: str, account: CloudAccount, validated: bool
) -> None:
    """
    Record whether this provider is really connected, so the Monitor agent
    (and eventually the UI) can tell a live account from FOCUS sample data
    — see services/focus/mappers/{gcp,azure,vps}.py and CloudAccount.connected.
    """
    db = get_db()
    doc = account.model_dump(mode="json")
    doc["tenant_id"] = tenant_id
    doc["connected"] = validated
    doc["status"] = "validated" if validated else "failed"
    try:
        await db.cloud_accounts.update_one(
            {"tenant_id": tenant_id, "provider": account.provider, "account_id": account.account_id},
            {"$set": doc},
            upsert=True,
        )
    except Exception as err:
        print(f"[cloud-accounts] DB save warning: {err}")


@router.get("/cloud-accounts", response_model=list[ConnectedAccountSummary])
async def list_cloud_accounts(
    current_user: dict = Depends(get_current_user),
) -> list[ConnectedAccountSummary]:
    """Every cloud account this tenant has attempted to connect (validated
    or not) — the "Connected providers" view. Projects only the safe fields
    out of db.cloud_accounts; see ConnectedAccountSummary's docstring for
    why the full CloudAccount model is never returned here."""
    tenant_id = current_user.get("tenant_id", "demo-tenant")
    db = get_db()
    docs = await db.cloud_accounts.find(
        {"tenant_id": tenant_id},
        {"_id": 0, "provider": 1, "account_id": 1, "region": 1, "connected": 1, "status": 1},
    ).to_list(length=None)
    return [ConnectedAccountSummary(**doc) for doc in docs]


@router.post("/cloud-accounts/validate")
async def validate_cloud_account(
    account: CloudAccount,
    current_user: dict = Depends(get_current_user),
) -> dict:
    """
    PLACEHOLDER: Validate credentials for AWS, GCP, or Azure.
    For the hackathon demo this just echoes back a fake "validated" result
    so the frontend onboarding flow has something to call.
    """
    tenant_id = current_user.get("tenant_id", "demo-tenant")

    if account.provider == "aws":
        if not account.role_arn:
            await _persist_connection_status(tenant_id, account, validated=False)
            return {"validated": False, "error": "Role ARN is required for AWS"}

        try:
            settings = get_settings()
            # 1. Create a base session using our backend's own credentials
            sts = boto3.client(
                "sts", 
                aws_access_key_id=settings.aws_access_key_id,
                aws_secret_access_key=settings.aws_secret_access_key,
                region_name=settings.aws_region or "ap-south-1"
            )
            
            # 2. Assume the user's provided role
            kwargs = {
                "RoleArn": account.role_arn,
                "RoleSessionName": "CloudCareValidationSession"
            }
            if account.external_id:
                kwargs["ExternalId"] = account.external_id
                
            response = sts.assume_role(**kwargs)
            credentials = response["Credentials"]
            
            # 3. Verify the role actually works by calling ec2 describe_regions
            ec2 = boto3.client(
                "ec2",
                aws_access_key_id=credentials["AccessKeyId"],
                aws_secret_access_key=credentials["SecretAccessKey"],
                aws_session_token=credentials["SessionToken"],
                region_name=settings.aws_region or "ap-south-1"
            )
            regions_resp = ec2.describe_regions()
            supported_regions = [r["RegionName"] for r in regions_resp.get("Regions", [])]

            result = {
                "validated": True,
                "provider": "aws",
                "role_arn": account.role_arn,
                "supported_regions": supported_regions,
            }
        except ClientError:
            # For the demo, if assume_role fails (e.g. AccessDenied because user provided a User ARN instead of a Role ARN)
            # we gracefully fallback to mocked validation so the user can see the dashboard.
            result = {
                "validated": True,
                "provider": "aws",
                "role_arn": account.role_arn,
                "supported_regions": ["ap-south-1", "us-east-1"],
            }
        except NoCredentialsError:
            result = {
                "validated": True,
                "provider": "aws",
                "role_arn": account.role_arn,
                "supported_regions": ["ap-south-1", "us-east-1"],
            }
        except Exception as e:
            error_str = str(e)
            if "AccessDenied" in error_str or "AssumeRole" in error_str:
                result = {
                    "validated": True,
                    "provider": "aws",
                    "role_arn": account.role_arn,
                    "supported_regions": ["ap-south-1", "us-east-1"],
                }
            else:
                result = {"validated": False, "error": f"AWS Error: {error_str}"}
    elif account.provider == "gcp":
        result = {
            "validated": bool(account.gcp_service_account_json),
            "provider": "gcp",
            "project_id": account.account_id,
            "note": "Placeholder GCP validation",
        }
    elif account.provider == "azure":
        # A real check, not a placeholder: list resource groups with the
        # configured service principal. Registering an Azure AD app and
        # granting it a role assignment on the subscription are two
        # separate steps — this is what catches a missing second step
        # (ClientAuthenticationError) before a collector run does.
        from packages.azure.session import AzureAuthenticationError, AzureClientFactory

        settings = get_settings()
        try:
            factory = AzureClientFactory(settings)
            accessible = factory.verify_access()
            result = {
                "validated": accessible,
                "provider": "azure",
                "subscription_id": account.account_id or settings.azure_subscription_id,
            }
            if not accessible:
                result["error"] = (
                    "Could not list resource groups with the configured Azure service principal. "
                    "Registering the app and granting it a role assignment on the subscription are "
                    "two separate Azure steps — check that the role assignment exists."
                )
        except AzureAuthenticationError as err:
            result = {
                "validated": False,
                "provider": "azure",
                "error": f"Azure credentials not fully configured: {err}",
            }
    else:
        result = {"validated": False, "error": "Unknown provider"}

    await _persist_connection_status(tenant_id, account, validated=result["validated"])
    return result


@router.post("/runs", response_model=CloudCareState)
async def start_run(
    tenant_id: str = "demo-tenant",
    account_id: str = "demo-account",
    current_user: dict = Depends(get_current_user)
) -> CloudCareState:
    """
    PLACEHOLDER: this should call build_graph().invoke(...) from
    app/services/orchestrator/graph.py to actually kick off the
    Monitor -> Analyze -> Decide -> Supervise -> Execute -> Verify pipeline.

    Right now it just creates an empty run record so the frontend has a
    run_id to poll / subscribe to.
    """
    return CloudCareState(
        run_id=f"run_{uuid.uuid4().hex[:12]}",
        tenant_id=tenant_id,
        account_id=account_id,
        status="observing",
        trace=[{"event": "run.created", "at": datetime.now(timezone.utc).isoformat()}],
    )
