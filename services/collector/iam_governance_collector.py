from __future__ import annotations

import json
from datetime import datetime, timezone

from botocore.exceptions import ClientError

from packages.aws.session import AWSClientFactory
from packages.schemas.governance import (
    AccountOverview,
    IAMPolicyRef,
    IAMUserDetail,
    ResourceCreator,
)
from services.collector.iam_collector import _oldest_active_key_age_days

# Event names that create a real, trackable resource — the set this
# collector attributes to a principal via CloudTrail. Anything else
# (reads, updates, deletes) is out of scope for "who created this."
RESOURCE_CREATION_EVENTS = (
    "RunInstances",
    "CreateBucket",
    "CreateFunction20150331",
    "CreateDBInstance",
    "CreateTable",
    "CreateDistribution",
    "CreateVpc",
    "CreateVolume",
)


class IAMGovernanceCollectionError(Exception):
    """Raised when a governance section cannot be collected at all."""


class IAMGovernanceCollector:
    """Account-wide identity/access structure + a CloudTrail-derived
    resource-creation audit trail — a different shape of data from the
    per-resource ResourceItem inventory (services/collector/iam_collector.py),
    so it's a separate collector rather than an extension of that one."""

    def __init__(self, client_factory: AWSClientFactory):
        self.client_factory = client_factory

    def get_account_overview(self) -> AccountOverview:
        iam = self.client_factory.client("iam", region_name="us-east-1")

        try:
            summary = iam.get_account_summary()["SummaryMap"]
        except ClientError as error:
            error_code = error.response.get("Error", {}).get("Code", "UNKNOWN_AWS_ERROR")
            raise IAMGovernanceCollectionError(f"Account overview failed: {error_code}") from error

        try:
            aliases = iam.list_account_aliases().get("AccountAliases", [])
            alias = aliases[0] if aliases else None
        except ClientError:
            alias = None

        try:
            iam.get_account_password_policy()
            password_policy_configured: bool | None = True
        except ClientError as error:
            if error.response.get("Error", {}).get("Code") == "NoSuchEntity":
                password_policy_configured = False
            else:
                password_policy_configured = None

        sts = self.client_factory.client("sts", region_name="us-east-1")
        account_id = sts.get_caller_identity()["Account"]

        return AccountOverview(
            account_id=account_id,
            alias=alias,
            root_mfa_enabled=bool(summary.get("AccountMFAEnabled")) if "AccountMFAEnabled" in summary else None,
            root_access_keys_present=bool(summary.get("AccountAccessKeysPresent"))
            if "AccountAccessKeysPresent" in summary
            else None,
            password_policy_configured=password_policy_configured,
        )

    def get_users_and_policies(self) -> list[IAMUserDetail]:
        iam = self.client_factory.client("iam", region_name="us-east-1")
        now = datetime.now(timezone.utc)

        try:
            paginator = iam.get_paginator("get_account_authorization_details")
            users: list[IAMUserDetail] = []
            for page in paginator.paginate(Filter=["User"]):
                for user in page.get("UserDetailList", []):
                    policies: list[IAMPolicyRef] = []
                    for managed in user.get("AttachedManagedPolicies", []):
                        policies.append(
                            IAMPolicyRef(
                                name=managed.get("PolicyName", "unknown"),
                                arn=managed.get("PolicyArn"),
                                type="managed",
                            )
                        )
                    for inline in user.get("UserPolicyList", []):
                        policies.append(
                            IAMPolicyRef(
                                name=inline.get("PolicyName", "unknown"),
                                type="inline",
                                document=inline.get("PolicyDocument"),
                            )
                        )

                    user_name = user["UserName"]
                    key_age = _oldest_active_key_age_days(iam, user_name, now)

                    users.append(
                        IAMUserDetail(
                            user_name=user_name,
                            arn=user["Arn"],
                            created_at=user.get("CreateDate"),
                            groups=user.get("GroupList", []),
                            policies=policies,
                            access_key_age_days=key_age,
                        )
                    )
        except ClientError as error:
            error_code = error.response.get("Error", {}).get("Code", "UNKNOWN_AWS_ERROR")
            raise IAMGovernanceCollectionError(f"Users/policies collection failed: {error_code}") from error

        return users

    def get_resource_creators(self, region: str, lookback_days: int = 90) -> list[ResourceCreator]:
        from datetime import timedelta

        cloudtrail = self.client_factory.client("cloudtrail", region_name=region)
        # CloudTrail's own hard limit is 90 trailing days without a
        # configured multi-year trail — this just makes that limit
        # explicit and enforced, rather than silently relying on whatever
        # CloudTrail happens to still have on hand.
        start_time = datetime.now(timezone.utc) - timedelta(days=lookback_days)

        try:
            paginator = cloudtrail.get_paginator("lookup_events")
            creators: list[ResourceCreator] = []
            for event_name in RESOURCE_CREATION_EVENTS:
                for page in paginator.paginate(
                    LookupAttributes=[{"AttributeKey": "EventName", "AttributeValue": event_name}],
                    StartTime=start_time,
                ):
                    for event in page.get("Events", []):
                        try:
                            detail = json.loads(event.get("CloudTrailEvent", "{}"))
                        except json.JSONDecodeError:
                            continue

                        user_identity = detail.get("userIdentity", {}) or {}
                        resources = detail.get("resources") or event.get("Resources") or []
                        resource_id = None
                        for res in resources:
                            resource_id = res.get("resourceName") if isinstance(res, dict) else None
                            if resource_id:
                                break
                        if not resource_id:
                            continue

                        creators.append(
                            ResourceCreator(
                                resource_id=resource_id,
                                event_name=event_name,
                                principal_arn=user_identity.get("arn"),
                                principal_name=user_identity.get("userName") or user_identity.get("arn"),
                                event_time=event.get("EventTime"),
                            )
                        )
        except ClientError as error:
            error_code = error.response.get("Error", {}).get("Code", "UNKNOWN_AWS_ERROR")
            raise IAMGovernanceCollectionError(f"Resource-creator lookup failed: {error_code}") from error

        return creators
