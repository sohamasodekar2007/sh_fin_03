"""
S3: lifecycle-suggestion-only, never anything touching permissions.

Explicit heuristic disclosure: "no access in 30 days" here is inferred
from CloudWatch's BucketSizeBytes staying flat (no growth/shrink signal),
NOT a real last-accessed timestamp — S3 doesn't expose per-object access
time without S3 Storage Lens (a paid, opt-in feature) or a full object
listing (expensive, not done here). This is stated in every
S3Recommendation's rationale, not hidden as if it were precise.
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Any

from botocore.exceptions import ClientError

from services.governance.tags import has_missing_ownership, is_excluded
from services.phase14.schemas import S3Recommendation

logger = logging.getLogger(__name__)

STABILITY_WINDOW_DAYS = 30


class S3AdvisorError(Exception):
    """Raised when S3 recommendations cannot be collected at all."""


def _bucket_size_series(cloudwatch: Any, bucket: str, region: str, days: int) -> list[float]:
    end = datetime.now(timezone.utc)
    start = end - timedelta(days=days)
    try:
        response = cloudwatch.get_metric_statistics(
            Namespace="AWS/S3",
            MetricName="BucketSizeBytes",
            Dimensions=[
                {"Name": "BucketName", "Value": bucket},
                {"Name": "StorageType", "Value": "StandardStorage"},
            ],
            StartTime=start,
            EndTime=end,
            Period=86400,
            Statistics=["Average"],
        )
    except ClientError as error:
        logger.info("phase14.s3_advisor: size metric failed for %s: %s", bucket, error)
        return []
    points = sorted(response.get("Datapoints", []), key=lambda p: p["Timestamp"])
    return [p["Average"] for p in points if "Average" in p]


def _bucket_tags(s3_client: Any, bucket: str) -> dict[str, str]:
    try:
        resp = s3_client.get_bucket_tagging(Bucket=bucket)
        return {t["Key"]: t["Value"] for t in resp.get("TagSet", [])}
    except ClientError:
        # NoSuchTagSet just means "no tags" — a real absence, not a failure.
        return {}


def _current_storage_class(s3_client: Any, bucket: str) -> str:
    try:
        lifecycle = s3_client.get_bucket_lifecycle_configuration(Bucket=bucket)
        rules = lifecycle.get("Rules", [])
        for rule in rules:
            for transition in rule.get("Transitions", []):
                storage_class = transition.get("StorageClass")
                if storage_class:
                    return storage_class
    except ClientError as error:
        # NoSuchLifecycleConfiguration is the common, honest "none set" case.
        if error.response.get("Error", {}).get("Code") != "NoSuchLifecycleConfiguration":
            logger.info("phase14.s3_advisor: lifecycle lookup failed for %s: %s", bucket, error)
    return "STANDARD"


class S3Advisor:
    def __init__(self, client_factory: Any, region: str):
        self.client_factory = client_factory
        self.region = region

    def collect_recommendations(self) -> list[S3Recommendation]:
        s3 = self.client_factory.client("s3", region_name="us-east-1")
        cloudwatch = self.client_factory.client("cloudwatch", region_name=self.region)

        try:
            buckets = s3.list_buckets().get("Buckets", [])
        except ClientError as error:
            error_code = error.response.get("Error", {}).get("Code", "UNKNOWN_AWS_ERROR")
            raise S3AdvisorError(f"S3 recommendation collection failed: {error_code}") from error

        recommendations: list[S3Recommendation] = []
        for bucket in buckets:
            name = bucket["Name"]
            tags = _bucket_tags(s3, name)
            if is_excluded(tags):
                continue

            current_class = _current_storage_class(s3, name)
            if current_class != "STANDARD":
                continue  # already transitioned — nothing to suggest

            sizes = _bucket_size_series(cloudwatch, name, self.region, STABILITY_WINDOW_DAYS)
            if len(sizes) < 2:
                continue  # not enough signal to say anything — never guess

            variation = (max(sizes) - min(sizes)) / max(sizes) if max(sizes) > 0 else 0.0
            if variation > 0.01:
                continue  # real size movement — not a stable/cold bucket

            rationale = (
                f"{name}'s size has stayed effectively flat (within {variation * 100:.2f}%) over the "
                f"trailing {STABILITY_WINDOW_DAYS} days — a heuristic for low activity, not a real "
                "last-accessed timestamp (S3 doesn't expose per-object access time without Storage "
                "Lens or a full object listing, neither done here). Standard-IA costs less for "
                "infrequently-accessed data; this is a lifecycle-transition suggestion only, no "
                "objects are moved or deleted automatically."
            )
            if has_missing_ownership(tags):
                rationale += (
                    " No Owner or Environment tag is set on this bucket — ownership is unclear, which "
                    "should factor into how quickly this gets approved."
                )

            recommendations.append(
                S3Recommendation(
                    bucket=name,
                    region=self.region,
                    current_storage_class=current_class,
                    suggested_storage_class="STANDARD_IA",
                    evidence={"size_variation_pct": round(variation * 100, 3), "window_days": STABILITY_WINDOW_DAYS},
                    rationale=rationale,
                )
            )

        return recommendations
