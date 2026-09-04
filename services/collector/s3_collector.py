from __future__ import annotations

from datetime import datetime, timezone

from botocore.exceptions import ClientError

from packages.aws.session import AWSClientFactory
from packages.schemas.cloud_resource import DependencyContext, S3BucketResourceRecord
from services.collector.ec2_collector import find_tag, normalize_environment, tags_to_dictionary
from services.governance.tags import has_missing_ownership


class S3CollectionError(Exception):
    """Raised when S3 bucket inventory cannot be collected."""


def _bucket_tags(s3_client, bucket_name: str) -> dict[str, str]:
    try:
        resp = s3_client.get_bucket_tagging(Bucket=bucket_name)
        return tags_to_dictionary(resp.get("TagSet"))
    except ClientError as error:
        # NoSuchTagSet just means "no tags" — a real absence, not a
        # collection failure, so it must not abort the whole bucket.
        if error.response.get("Error", {}).get("Code") == "NoSuchTagSet":
            return {}
        return {}


def _bucket_region(s3_client, bucket_name: str, default_region: str) -> str:
    try:
        resp = s3_client.get_bucket_location(Bucket=bucket_name)
        # AWS quirk: us-east-1 buckets report LocationConstraint as None.
        return resp.get("LocationConstraint") or "us-east-1"
    except ClientError:
        return default_region


def normalize_bucket(
    bucket: dict,
    tags: dict[str, str],
    region: str,
    collected_at: datetime,
) -> S3BucketResourceRecord:
    name = bucket["Name"]
    environment = normalize_environment(tags)

    warnings: list[str] = []
    if not tags:
        warnings.append("RESOURCE_HAS_NO_TAGS")

    return S3BucketResourceRecord(
        region=region,
        resource_id=name,
        name=find_tag(tags, "Name") or name,
        environment=environment,
        instance_type="bucket",
        state="active",
        launched_at=bucket.get("CreationDate"),
        collected_at=collected_at,
        tags=tags,
        warnings=warnings,
        dependency_context=DependencyContext(missing_ownership=has_missing_ownership(tags)),
    )


class S3Collector:
    """S3 is a global service — ListBuckets always goes through us-east-1
    regardless of the account's working region, matching how
    AWSClientFactory.client("ce", ...) already special-cases Cost Explorer."""

    def __init__(self, client_factory: AWSClientFactory, region: str):
        self.client_factory = client_factory
        self.region = region

    def collect(self) -> list[S3BucketResourceRecord]:
        s3 = self.client_factory.client("s3", region_name="us-east-1")
        collected_at = datetime.now(timezone.utc)

        try:
            response = s3.list_buckets()
        except ClientError as error:
            error_code = error.response.get("Error", {}).get("Code", "UNKNOWN_AWS_ERROR")
            raise S3CollectionError(f"S3 collection failed: {error_code}") from error

        buckets: list[S3BucketResourceRecord] = []
        for bucket in response.get("Buckets", []):
            name = bucket["Name"]
            bucket_region = _bucket_region(s3, name, self.region)
            tags = _bucket_tags(s3, name)
            buckets.append(
                normalize_bucket(
                    bucket=bucket,
                    tags=tags,
                    region=bucket_region,
                    collected_at=collected_at,
                )
            )

        return buckets
