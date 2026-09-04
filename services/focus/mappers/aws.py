"""
Maps AWS billing data into FOCUS 1.0 rows.

SOURCE STRATEGY (both, with fallback): first try to read a real AWS Data
Exports FOCUS 1.0 delivery from s3://{bucket}/{prefix}; if the bucket is
unset, empty, or unreadable, fall back to synthesizing FOCUS rows from the
CloudSnapshot the Monitor agent already collected. FocusDataset.source
records which path was actually taken ("live_export" | "synthesized") so
the UI can label the data honestly.

WHY SYNTHESIS IS AN ALLOCATION, NOT A TRUE BREAKDOWN: CloudSnapshot.daily_costs
comes from services/collector/cost_collector.py's Cost Explorer call, which
returns one UNBLENDED total per day for the whole account/region — it has no
per-resource dimension (see packages/schemas/cloud_metrics.py:DailyCost —
no resource_id field). There is no true per-resource cost breakdown
available without Cost Categories / cost allocation tags configured in Cost
Explorer, which this collector doesn't set up. So each day's account total
is split evenly across the resources present in the snapshot that day, and
every synthesized row is tagged with extensions["x_allocation_method"] so a
consumer can never mistake it for an observed per-resource cost.
"""

from __future__ import annotations

import csv
import gzip
import io
import logging
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from typing import Any

from packages.schemas.focus import FocusDataset, FocusRecord

logger = logging.getLogger(__name__)


def _decimal(value: Any) -> Decimal:
    if isinstance(value, Decimal):
        return value
    if value is None:
        return Decimal("0")
    try:
        return Decimal(str(value))
    except Exception:  # noqa: BLE001
        return Decimal("0")


def _resource_id(resource: dict[str, Any]) -> str | None:
    return resource.get("resource_id") or resource.get("instance_id") or resource.get("id")


def _service_fields(resource_type: str | None) -> tuple[str, str]:
    """(ServiceName, ServiceCategory) for a CloudCare resource_type.

    Branches by resource_type rather than a single hardcoded Compute value:
    Phase 3's analyzer detects unattached EBS volumes via
    ServiceCategory == "Storage", so collapsing every resource onto
    "Compute" would silently break that rule.
    """
    if resource_type == "ebs_volume":
        return "Amazon Elastic Block Store", "Storage"
    if resource_type == "s3_bucket":
        return "Amazon Simple Storage Service", "Storage"
    if resource_type == "rds_instance":
        return "Amazon Relational Database Service", "Databases"
    if resource_type == "lambda_function":
        return "AWS Lambda", "Compute"
    if resource_type == "dynamodb_table":
        return "Amazon DynamoDB", "Databases"
    if resource_type == "cloudfront_distribution":
        return "Amazon CloudFront", "Networking"
    if resource_type == "vpc":
        return "Amazon Virtual Private Cloud", "Networking"
    if resource_type == "iam_user":
        return "AWS Identity and Access Management", "Identity"
    # Default / ec2_instance / anything unrecognized.
    return "Amazon Elastic Compute Cloud - Compute", "Compute"


def _billing_period_bounds(charge_start: datetime) -> tuple[datetime, datetime]:
    month_start = charge_start.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    if month_start.month == 12:
        next_month_start = month_start.replace(year=month_start.year + 1, month=1)
    else:
        next_month_start = month_start.replace(month=month_start.month + 1)
    return month_start, next_month_start


def _synthesize_from_snapshot(snapshot: dict[str, Any], tenant_id: str, focus_version: str = "1.2") -> FocusDataset:
    account_id = str(snapshot.get("account_id", ""))
    resources: list[dict[str, Any]] = snapshot.get("resources") or []
    daily_costs: list[dict[str, Any]] = snapshot.get("daily_costs") or []

    records: list[FocusRecord] = []
    warnings: list[str] = []
    row_index = 0

    if not resources and not daily_costs:
        return FocusDataset(
            tenant_id=tenant_id,
            provider="aws",
            account_id=account_id,
            focus_version=focus_version,
            granularity="daily",
            source="synthesized",
            row_count=0,
            records=[],
            warnings=["empty_snapshot_no_resources_or_costs"],
        )

    resource_count = max(len(resources), 1)

    if daily_costs and resources:
        for day_entry in daily_costs:
            usage_date = day_entry.get("usage_date")
            if isinstance(usage_date, str):
                usage_date = date.fromisoformat(usage_date)
            elif isinstance(usage_date, datetime):
                usage_date = usage_date.date()
            if not isinstance(usage_date, date):
                warnings.append(f"unparseable_usage_date:row_{row_index}")
                continue

            charge_start = datetime(usage_date.year, usage_date.month, usage_date.day, tzinfo=timezone.utc)
            charge_end = charge_start + timedelta(days=1)
            billing_start, billing_end = _billing_period_bounds(charge_start)

            day_total = _decimal(day_entry.get("amount"))
            per_resource_share = day_total / resource_count

            for resource in resources:
                resource_type = resource.get("resource_type")
                service_name, service_category = _service_fields(resource_type)
                resource_id = _resource_id(resource)

                raw = {
                    "BillingAccountId": account_id,
                    "BillingPeriodStart": billing_start,
                    "BillingPeriodEnd": billing_end,
                    "ChargePeriodStart": charge_start,
                    "ChargePeriodEnd": charge_end,
                    "ChargeCategory": "Usage",
                    "ChargeDescription": (
                        f"Allocated share of {usage_date.isoformat()} AWS Cost Explorer "
                        f"{day_entry.get('metric', 'UnblendedCost')} for {resource_id or 'account'}"
                    ),
                    "ChargeFrequency": "Usage-Based",
                    "BilledCost": per_resource_share,
                    "EffectiveCost": per_resource_share,
                    "BillingCurrency": day_entry.get("currency", "USD"),
                    "ProviderName": "AWS",
                    "PublisherName": "AWS",
                    "RegionId": resource.get("region") or snapshot.get("region"),
                    "AvailabilityZone": resource.get("availability_zone"),
                    "ResourceId": resource_id,
                    "ResourceName": resource.get("name"),
                    "ResourceType": resource_type,
                    "ServiceCategory": service_category,
                    "ServiceName": service_name,
                    "SkuId": resource.get("instance_type"),
                    "Tags": resource.get("tags") or {},
                }

                extensions = {
                    "x_allocation_method": "equal_split_of_account_daily_cost",
                    "x_resource_count_in_snapshot": resource_count,
                }
                # Carries the resource's raw state ("available"/"in-use" for
                # EBS, "running"/"stopped" for EC2, etc) through to FOCUS so
                # the Analyzer's unattached-storage rule (Phase 3) doesn't
                # need provider-specific ID string matching to find it.
                if resource.get("state") is not None:
                    extensions["x_resource_state"] = resource.get("state")
                source_warnings = resource.get("warnings")
                if source_warnings:
                    extensions["x_source_resource_warnings"] = source_warnings
                raw["extensions"] = extensions

                record, row_warnings = FocusRecord.from_raw(raw)
                warnings.extend(f"{w}:row_{row_index}" for w in row_warnings)
                records.append(record)
                row_index += 1

    elif resources and not daily_costs:
        # No cost data at all (e.g. Cost Explorer failed) — still emit one
        # row per discovered resource rather than dropping it, at $0, with
        # a warning flagging the missing cost data.
        collected_at = snapshot.get("collected_at")
        if isinstance(collected_at, str):
            charge_start = datetime.fromisoformat(collected_at)
        elif isinstance(collected_at, datetime):
            charge_start = collected_at
        else:
            charge_start = datetime.now(timezone.utc)
        if charge_start.tzinfo is None:
            charge_start = charge_start.replace(tzinfo=timezone.utc)
        charge_start = charge_start.replace(hour=0, minute=0, second=0, microsecond=0)
        charge_end = charge_start + timedelta(days=1)
        billing_start, billing_end = _billing_period_bounds(charge_start)

        for resource in resources:
            resource_type = resource.get("resource_type")
            service_name, service_category = _service_fields(resource_type)
            resource_id = _resource_id(resource)

            raw = {
                "BillingAccountId": account_id,
                "BillingPeriodStart": billing_start,
                "BillingPeriodEnd": billing_end,
                "ChargePeriodStart": charge_start,
                "ChargePeriodEnd": charge_end,
                "ChargeCategory": "Usage",
                "ChargeDescription": f"No Cost Explorer data available for {resource_id or 'resource'}",
                "BilledCost": Decimal("0"),
                "EffectiveCost": Decimal("0"),
                "BillingCurrency": "USD",
                "ProviderName": "AWS",
                "PublisherName": "AWS",
                "RegionId": resource.get("region") or snapshot.get("region"),
                "AvailabilityZone": resource.get("availability_zone"),
                "ResourceId": resource_id,
                "ResourceName": resource.get("name"),
                "ResourceType": resource_type,
                "ServiceCategory": service_category,
                "ServiceName": service_name,
                "SkuId": resource.get("instance_type"),
                "Tags": resource.get("tags") or {},
                "extensions": {
                    "x_allocation_method": "no_cost_data_available",
                    **({"x_resource_state": resource.get("state")} if resource.get("state") is not None else {}),
                },
            }
            record, row_warnings = FocusRecord.from_raw(raw)
            warnings.append(f"no_cost_data_available_for_resource:row_{row_index}")
            warnings.extend(f"{w}:row_{row_index}" for w in row_warnings)
            records.append(record)
            row_index += 1

    logger.info(
        "focus.aws_mapper: synthesized %d FOCUS rows from CloudSnapshot for tenant=%s account=%s "
        "(%d resources, %d cost-days, %d warnings)",
        len(records), tenant_id, account_id, len(resources), len(daily_costs), len(warnings),
    )

    return FocusDataset(
        tenant_id=tenant_id,
        provider="aws",
        account_id=account_id,
        focus_version=focus_version,
        granularity="daily",
        source="synthesized",
        row_count=len(records),
        records=records,
        warnings=warnings,
    )


def _read_live_export(
    bucket: str,
    prefix: str,
    tenant_id: str,
    account_id: str,
    aws_access_key_id: str | None = None,
    aws_secret_access_key: str | None = None,
    region_name: str | None = None,
    focus_version: str = "1.2",
) -> FocusDataset | None:
    """
    Read the most recent AWS Data Exports FOCUS 1.0/1.2 delivery (Parquet or
    gzipped/plain CSV) from s3://{bucket}/{prefix}. Returns None — never
    raises — if the bucket is unset, empty, unreadable, or the object can't
    be parsed, so the caller always has a safe fallback to synthesis.

    Credentials are explicit args, not boto3's default chain: pydantic-settings
    reads AWS_ACCESS_KEY_ID/AWS_SECRET_ACCESS_KEY out of .env into
    Settings, but never injects them into os.environ, so a bare
    boto3.client("s3") here would silently fall through to "no credentials
    found" even with a fully-populated .env. When both are unset (e.g. an
    EC2 instance profile in production), boto3 still falls back to its own
    default chain, since None is the same as omitting the kwarg.
    """
    if not bucket:
        return None

    try:
        import boto3
    except ImportError:
        logger.warning("focus.aws_mapper: boto3 unavailable, skipping live_export path")
        return None

    try:
        s3 = boto3.client(
            "s3",
            aws_access_key_id=aws_access_key_id or None,
            aws_secret_access_key=aws_secret_access_key or None,
            region_name=region_name or None,
        )
        paginator = s3.get_paginator("list_objects_v2")
        candidates: list[dict[str, Any]] = []
        for page in paginator.paginate(Bucket=bucket, Prefix=prefix):
            for obj in page.get("Contents", []):
                key = obj["Key"]
                if key.endswith((".csv.gz", ".csv", ".parquet")):
                    candidates.append(obj)

        if not candidates:
            logger.info("focus.aws_mapper: no FOCUS export objects under s3://%s/%s", bucket, prefix)
            return None

        latest = max(candidates, key=lambda o: o["LastModified"])
        key = latest["Key"]
        logger.info("focus.aws_mapper: reading live FOCUS export s3://%s/%s", bucket, key)

        body = s3.get_object(Bucket=bucket, Key=key)["Body"].read()

        if key.endswith(".parquet"):
            try:
                import pyarrow.parquet as pq
            except ImportError:
                logger.warning(
                    "focus.aws_mapper: %s is Parquet but pyarrow is not installed, "
                    "skipping live_export and falling back to synthesis", key,
                )
                return None
            rows = pq.read_table(io.BytesIO(body)).to_pylist()
        else:
            raw_bytes = gzip.decompress(body) if key.endswith(".gz") else body
            rows = list(csv.DictReader(io.StringIO(raw_bytes.decode("utf-8"))))

        records: list[FocusRecord] = []
        warnings: list[str] = []
        for i, row in enumerate(rows):
            record, row_warnings = FocusRecord.from_raw(row)
            warnings.extend(f"{w}:row_{i}" for w in row_warnings)
            records.append(record)

        return FocusDataset(
            tenant_id=tenant_id,
            provider="aws",
            account_id=account_id,
            focus_version=focus_version,
            granularity="daily",
            source="live_export",
            row_count=len(records),
            records=records,
            warnings=warnings,
        )

    except Exception as exc:  # noqa: BLE001 - any S3/parse failure falls back to synthesis
        logger.info("focus.aws_mapper: live_export read failed (%s), falling back to synthesis", exc)
        return None


def map_snapshot_to_focus(
    snapshot: dict[str, Any],
    tenant_id: str,
    s3_bucket: str = "",
    s3_prefix: str = "",
    aws_access_key_id: str | None = None,
    aws_secret_access_key: str | None = None,
    aws_region: str | None = None,
    focus_version: str = "1.2",
) -> FocusDataset:
    """
    Map an AWS CloudSnapshot dict into a FocusDataset. Tries a real FOCUS
    Data Export from S3 first (if s3_bucket is configured); falls back to
    synthesizing rows from the CloudSnapshot otherwise.
    """
    account_id = str(snapshot.get("account_id", ""))

    live = _read_live_export(
        s3_bucket, s3_prefix, tenant_id, account_id,
        aws_access_key_id=aws_access_key_id,
        aws_secret_access_key=aws_secret_access_key,
        region_name=aws_region,
        focus_version=focus_version,
    )
    if live is not None:
        return live

    return _synthesize_from_snapshot(snapshot, tenant_id, focus_version=focus_version)
