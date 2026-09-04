from __future__ import annotations

from datetime import datetime, timezone

from botocore.exceptions import ClientError

from packages.aws.session import AWSClientFactory
from packages.schemas.cloud_resource import CloudFrontDistributionResourceRecord
from services.collector.ec2_collector import normalize_environment


class CloudFrontCollectionError(Exception):
    """Raised when CloudFront distribution inventory cannot be collected."""


def _distribution_tags(cf_client, arn: str) -> dict[str, str]:
    try:
        resp = cf_client.list_tags_for_resource(Resource=arn)
        return {t["Key"]: t.get("Value", "") for t in resp.get("Tags", {}).get("Items", [])}
    except ClientError:
        return {}


def normalize_distribution(
    dist: dict,
    tags: dict[str, str],
    collected_at: datetime,
) -> CloudFrontDistributionResourceRecord:
    resource_id = dist["Id"]
    environment = normalize_environment(tags)

    warnings: list[str] = []
    if not tags:
        warnings.append("RESOURCE_HAS_NO_TAGS")
    if not dist.get("Enabled", True):
        warnings.append("DISTRIBUTION_DISABLED")

    return CloudFrontDistributionResourceRecord(
        region="global",
        resource_id=resource_id,
        name=dist.get("DomainName", resource_id),
        environment=environment,
        instance_type=dist.get("PriceClass", "unknown"),
        state="enabled" if dist.get("Enabled") else "disabled",
        launched_at=dist.get("LastModifiedTime"),
        collected_at=collected_at,
        tags=tags,
        warnings=warnings,
    )


class CloudFrontCollector:
    """Global service — always us-east-1, matching S3/IAM."""

    def __init__(self, client_factory: AWSClientFactory):
        self.client_factory = client_factory

    def collect(self) -> list[CloudFrontDistributionResourceRecord]:
        cf = self.client_factory.client("cloudfront", region_name="us-east-1")
        collected_at = datetime.now(timezone.utc)

        distributions: list[CloudFrontDistributionResourceRecord] = []
        try:
            paginator = cf.get_paginator("list_distributions")
            for page in paginator.paginate():
                items = page.get("DistributionList", {}).get("Items", [])
                for dist in items:
                    tags = _distribution_tags(cf, dist.get("ARN", ""))
                    distributions.append(normalize_distribution(dist, tags, collected_at))
        except ClientError as error:
            error_code = error.response.get("Error", {}).get("Code", "UNKNOWN_AWS_ERROR")
            raise CloudFrontCollectionError(f"CloudFront collection failed: {error_code}") from error

        return distributions
