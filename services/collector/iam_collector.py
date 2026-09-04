from __future__ import annotations

from datetime import datetime, timezone

from botocore.exceptions import ClientError

from packages.aws.session import AWSClientFactory
from packages.schemas.cloud_resource import IAMUserResourceRecord
from services.collector.ec2_collector import normalize_environment


class IAMCollectionError(Exception):
    """Raised when IAM user inventory cannot be collected."""


# Access-key age past which a key is flagged as a rotation-hygiene finding —
# a common security baseline (CIS AWS Foundations 1.14), not a cost signal.
STALE_KEY_AGE_DAYS = 90


def _user_tags(iam_client, user_name: str) -> dict[str, str]:
    try:
        resp = iam_client.list_user_tags(UserName=user_name)
        return {t["Key"]: t["Value"] for t in resp.get("Tags", [])}
    except ClientError:
        return {}


def _oldest_active_key_age_days(iam_client, user_name: str, now: datetime) -> int | None:
    try:
        resp = iam_client.list_access_keys(UserName=user_name)
    except ClientError:
        return None
    ages = [
        (now - key["CreateDate"]).days
        for key in resp.get("AccessKeyMetadata", [])
        if key.get("Status") == "Active"
    ]
    return max(ages) if ages else None


def normalize_user(
    user: dict,
    tags: dict[str, str],
    key_age_days: int | None,
    collected_at: datetime,
) -> IAMUserResourceRecord:
    resource_id = user["UserName"]
    environment = normalize_environment(tags)

    warnings: list[str] = []
    if not tags:
        warnings.append("RESOURCE_HAS_NO_TAGS")
    if key_age_days is not None and key_age_days >= STALE_KEY_AGE_DAYS:
        warnings.append("STALE_ACCESS_KEY")

    state = f"key-age-{key_age_days}d" if key_age_days is not None else "no-active-key"

    return IAMUserResourceRecord(
        region="global",
        resource_id=resource_id,
        name=resource_id,
        environment=environment,
        instance_type="iam_user",
        state=state,
        launched_at=user.get("CreateDate"),
        collected_at=collected_at,
        tags=tags,
        warnings=warnings,
    )


class IAMCollector:
    """Security/hygiene inventory (stale access keys), not a cost source —
    IAM has no billable unit, so monthly_cost_usd stays None for every
    record this produces (observation.py's FOCUS-cost join never finds a
    matching ResourceId here, which is correct)."""

    def __init__(self, client_factory: AWSClientFactory):
        self.client_factory = client_factory

    def collect(self) -> list[IAMUserResourceRecord]:
        iam = self.client_factory.client("iam", region_name="us-east-1")
        paginator = iam.get_paginator("list_users")
        collected_at = datetime.now(timezone.utc)

        users: list[IAMUserResourceRecord] = []
        try:
            for page in paginator.paginate():
                for user in page.get("Users", []):
                    user_name = user["UserName"]
                    tags = _user_tags(iam, user_name)
                    key_age = _oldest_active_key_age_days(iam, user_name, collected_at)
                    users.append(normalize_user(user, tags, key_age, collected_at))
        except ClientError as error:
            error_code = error.response.get("Error", {}).get("Code", "UNKNOWN_AWS_ERROR")
            raise IAMCollectionError(f"IAM collection failed: {error_code}") from error

        return users
