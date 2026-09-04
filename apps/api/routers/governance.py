"""
IAM & Governance router — "who can do what, and who created what." Read-
through, no Mongo persistence: this is a point-in-time account snapshot,
not something the Analyzer/Decision pipeline consumes the way db.resources
is, so there's nothing to sync.
"""

from __future__ import annotations

from fastapi import APIRouter

from apps.api.config import get_settings
from apps.api.dependencies import CurrentUser
from packages.aws.session import AWSClientFactory
from packages.schemas.governance import AccountOverview, IAMGovernanceOverview
from services.collector.iam_governance_collector import (
    IAMGovernanceCollectionError,
    IAMGovernanceCollector,
)

router = APIRouter(prefix="/v1/governance", tags=["governance"])


def _direct_credentials_factory(settings) -> AWSClientFactory | None:
    if not settings.aws_access_key_id or not settings.aws_secret_access_key:
        return None
    direct_settings = settings.model_copy(update={"aws_role_arn": "", "aws_read_role_arn": ""})
    return AWSClientFactory(direct_settings)


def _is_access_denied(error: Exception) -> bool:
    return "AccessDenied" in str(error) or "AccessDeniedException" in str(error)


@router.get("/iam-overview", response_model=IAMGovernanceOverview)
async def get_iam_overview(current_user: CurrentUser) -> IAMGovernanceOverview:
    settings = get_settings()
    factory = AWSClientFactory(settings)
    direct_factory = _direct_credentials_factory(settings)
    collector = IAMGovernanceCollector(client_factory=factory)

    errors: dict[str, str] = {}

    try:
        account = collector.get_account_overview()
    except IAMGovernanceCollectionError as error:
        if direct_factory is not None and _is_access_denied(error):
            try:
                account = IAMGovernanceCollector(client_factory=direct_factory).get_account_overview()
            except IAMGovernanceCollectionError as fallback_error:
                account = AccountOverview(account_id=settings.aws_account_id or "unknown")
                errors["account"] = str(fallback_error)
        else:
            account = AccountOverview(account_id=settings.aws_account_id or "unknown")
            errors["account"] = str(error)

    try:
        users = collector.get_users_and_policies()
    except IAMGovernanceCollectionError as error:
        if direct_factory is not None and _is_access_denied(error):
            try:
                users = IAMGovernanceCollector(client_factory=direct_factory).get_users_and_policies()
            except IAMGovernanceCollectionError as fallback_error:
                users = []
                errors["users"] = str(fallback_error)
        else:
            users = []
            errors["users"] = str(error)

    try:
        resource_creators = collector.get_resource_creators(region=settings.aws_region)
    except IAMGovernanceCollectionError as error:
        if direct_factory is not None and _is_access_denied(error):
            try:
                resource_creators = IAMGovernanceCollector(client_factory=direct_factory).get_resource_creators(
                    region=settings.aws_region
                )
            except IAMGovernanceCollectionError as fallback_error:
                resource_creators = []
                errors["resource_creators"] = str(fallback_error)
        else:
            resource_creators = []
            errors["resource_creators"] = str(error)

    return IAMGovernanceOverview(
        account=account,
        users=users,
        resource_creators=resource_creators,
        errors=errors,
    )
