from __future__ import annotations

import json
from io import BytesIO
from collections import Counter, defaultdict
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any

from fastapi import APIRouter, HTTPException, Query
from fastapi.encoders import jsonable_encoder
from botocore.exceptions import ClientError

from apps.api.config import get_settings
from apps.api.dependencies import CurrentUser
from packages.aws.session import AWSClientFactory

router = APIRouter(prefix="/v1/parquet-analysis", tags=["parquet-analysis"])

COST_COLUMNS = ("BilledCost", "EffectiveCost", "ListCost", "ContractedCost")


def _load_table(raw_bytes: bytes, limit: int):
    try:
        import pyarrow.parquet as pq
    except ImportError as exc:
        raise HTTPException(status_code=500, detail="pyarrow is required to inspect Parquet files.") from exc

    parquet_file = pq.ParquetFile(BytesIO(raw_bytes))
    table = parquet_file.read()
    return parquet_file, table, table.slice(0, limit)


def _number(value: Any) -> float:
    if value is None:
        return 0.0
    if isinstance(value, Decimal):
        return float(value)
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def _top(rows: list[dict[str, Any]], label_key: str, value_key: str = "BilledCost", limit: int = 8) -> list[dict[str, Any]]:
    totals: dict[str, float] = defaultdict(float)
    counts: Counter[str] = Counter()
    for row in rows:
        label = str(row.get(label_key) or "Unknown")
        totals[label] += _number(row.get(value_key))
        counts[label] += 1
    return [
        {"name": name, "cost_usd": round(cost, 4), "rows": counts[name]}
        for name, cost in sorted(totals.items(), key=lambda item: item[1], reverse=True)[:limit]
    ]


def _converter_plan(settings) -> dict[str, Any]:
    bucket = settings.focus_export_s3_bucket
    prefix = settings.focus_export_s3_prefix.strip("/")
    key = f"{prefix + '/' if prefix else ''}parquet-analysis/latest.json"
    return {
        "cadence_minutes": 60,
        "scheduler_interval_minutes": settings.scheduler_interval_minutes,
        "parquet_analysis_interval_minutes": settings.parquet_analysis_interval_minutes,
        "s3_configured": bool(bucket),
        "bucket": bucket or None,
        "prefix": prefix,
        "target_key": key,
        "target_uri": f"s3://{bucket}/{key}" if bucket else None,
        "formats": ["json-summary", "csv-preview", "focus-normalized-json", "snappy-parquet"],
        "compression": "snappy",
        "mode": "automatic S3 source and automatic hourly S3 summary rewrite",
    }


def _s3_client(settings, *, access: str = "read"):
    effective_settings = settings
    if access == "write" and settings.aws_write_role_arn:
        effective_settings = settings.model_copy(
            update={
                "aws_role_arn": settings.aws_write_role_arn,
                "aws_read_role_arn": "",
            }
        )
    return AWSClientFactory(effective_settings).client("s3", region_name=settings.aws_region)


def _require_s3_config(settings) -> tuple[str, str]:
    bucket = settings.focus_export_s3_bucket.strip()
    prefix = settings.focus_export_s3_prefix.strip("/")
    if not bucket:
        raise HTTPException(
            status_code=503,
            detail="FOCUS_EXPORT_S3_BUCKET is required. Parquet analysis is S3-only.",
        )
    return bucket, prefix


def _latest_parquet_object(settings) -> dict[str, Any]:
    bucket, prefix = _require_s3_config(settings)
    s3 = _s3_client(settings, access="read")
    paginator = s3.get_paginator("list_objects_v2")
    latest: dict[str, Any] | None = None
    try:
        for page in paginator.paginate(Bucket=bucket, Prefix=f"{prefix}/" if prefix else ""):
            for item in page.get("Contents", []):
                key = item.get("Key", "")
                if not key.lower().endswith(".parquet"):
                    continue
                if latest is None or item["LastModified"] > latest["LastModified"]:
                    latest = item
    except ClientError as exc:
        code = exc.response.get("Error", {}).get("Code", "S3Error")
        message = exc.response.get("Error", {}).get("Message", str(exc))
        raise HTTPException(
            status_code=403,
            detail=f"S3 list failed for s3://{bucket}/{prefix}: {code} - {message}",
        ) from exc
    if latest is None:
        raise HTTPException(status_code=404, detail=f"No .parquet objects found in s3://{bucket}/{prefix}")
    return {"bucket": bucket, "key": latest["Key"], "size_bytes": latest.get("Size", 0), "last_modified": latest["LastModified"]}


def _read_s3_parquet(settings) -> tuple[dict[str, Any], bytes]:
    source = _latest_parquet_object(settings)
    s3 = _s3_client(settings, access="read")
    try:
        body = s3.get_object(Bucket=source["bucket"], Key=source["key"])["Body"].read()
    except ClientError as exc:
        code = exc.response.get("Error", {}).get("Code", "S3Error")
        message = exc.response.get("Error", {}).get("Message", str(exc))
        raise HTTPException(
            status_code=403,
            detail=f"S3 read failed for s3://{source['bucket']}/{source['key']}: {code} - {message}",
        ) from exc
    return source, body


def build_parquet_analysis_payload(
    *,
    source: dict[str, Any],
    raw_bytes: bytes,
    sample_limit: int,
    tenant_id: str,
    settings: Any,
) -> dict[str, Any]:
    parquet_file, table, sample = _load_table(raw_bytes, sample_limit)
    rows = table.to_pylist()
    sample_rows = sample.to_pylist()
    metadata = parquet_file.metadata
    schema = table.schema

    cost_totals = {
        column: round(sum(_number(row.get(column)) for row in rows), 4)
        for column in COST_COLUMNS
        if column in table.column_names
    }
    distinct_resources = len({row.get("ResourceId") for row in rows if row.get("ResourceId")})
    distinct_services = len({row.get("ServiceName") for row in rows if row.get("ServiceName")})
    billed = cost_totals.get("BilledCost", 0.0)
    effective = cost_totals.get("EffectiveCost", 0.0)
    list_cost = cost_totals.get("ListCost", 0.0)

    source_uri = f"s3://{source['bucket']}/{source['key']}"
    return jsonable_encoder(
        {
            "file": {
                "source": "s3",
                "uri": source_uri,
                "bucket": source["bucket"],
                "key": source["key"],
                "name": source["key"].split("/")[-1],
                "size_bytes": source["size_bytes"],
                "compression": "snappy" if "snappy" in source["key"].lower() else "unknown",
                "last_modified": source["last_modified"],
            },
            "summary": {
                "tenant_id": tenant_id,
                "rows": metadata.num_rows,
                "columns": metadata.num_columns,
                "row_groups": metadata.num_row_groups,
                "distinct_resources": distinct_resources,
                "distinct_services": distinct_services,
                "billed_cost_usd": round(billed, 4),
                "effective_cost_usd": round(effective, 4),
                "list_cost_usd": round(list_cost, 4),
                "savings_vs_list_usd": round(max(list_cost - effective, 0), 4),
            },
            "schema": [
                {"name": field.name, "type": str(field.type), "nullable": field.nullable}
                for field in schema
            ],
            "breakdowns": {
                "by_service": _top(rows, "ServiceName"),
                "by_category": _top(rows, "ServiceCategory"),
                "by_region": _top(rows, "RegionName"),
                "by_charge_category": _top(rows, "ChargeCategory"),
            },
            "sample_rows": sample_rows,
            "converter": _converter_plan(settings),
            "generated_at": datetime.now(timezone.utc).isoformat(),
        }
    )


def refresh_s3_parquet_analysis(tenant_id: str = "demo-tenant", sample_limit: int = 50) -> dict[str, Any]:
    settings = get_settings()
    plan = _converter_plan(settings)
    source, raw_bytes = _read_s3_parquet(settings)
    payload = build_parquet_analysis_payload(
        source=source,
        raw_bytes=raw_bytes,
        sample_limit=sample_limit,
        tenant_id=tenant_id,
        settings=settings,
    )
    s3 = _s3_client(settings, access="write")
    try:
        s3.put_object(
            Bucket=plan["bucket"],
            Key=plan["target_key"],
            Body=json.dumps(payload).encode("utf-8"),
            ContentType="application/json",
            ServerSideEncryption="AES256",
        )
    except ClientError as exc:
        code = exc.response.get("Error", {}).get("Code", "S3Error")
        message = exc.response.get("Error", {}).get("Message", str(exc))
        raise HTTPException(
            status_code=403,
            detail=f"S3 rewrite failed for {plan['target_uri']}: {code} - {message}",
        ) from exc
    return {
        "status": "rewritten",
        "source_uri": payload["file"]["uri"],
        "target_uri": plan["target_uri"],
        "rewritten_at": datetime.now(timezone.utc).isoformat(),
        "plan": plan,
    }


@router.get("", response_model=dict[str, Any])
async def inspect_parquet(
    current_user: CurrentUser,
    sample_limit: int = Query(default=50, ge=1, le=200),
) -> dict[str, Any]:
    settings = get_settings()
    source, raw_bytes = _read_s3_parquet(settings)
    return build_parquet_analysis_payload(
        source=source,
        raw_bytes=raw_bytes,
        sample_limit=sample_limit,
        tenant_id=current_user["tenant_id"],
        settings=settings,
    )


@router.post("/rewrite-s3", response_model=dict[str, Any])
async def rewrite_s3_analysis(current_user: CurrentUser) -> dict[str, Any]:
    return refresh_s3_parquet_analysis(tenant_id=current_user["tenant_id"])
