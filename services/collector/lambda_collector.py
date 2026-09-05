from __future__ import annotations

from datetime import datetime, timezone

from botocore.exceptions import ClientError

from packages.aws.session import AWSClientFactory
from packages.schemas.cloud_resource import LambdaFunctionResourceRecord
from services.collector.ec2_collector import normalize_environment


class LambdaCollectionError(Exception):
    """Raised when Lambda function inventory cannot be collected."""


def _function_tags(lambda_client, function_arn: str) -> dict[str, str]:
    try:
        resp = lambda_client.list_tags(Resource=function_arn)
        return {str(k): str(v) for k, v in (resp.get("Tags") or {}).items()}
    except ClientError:
        return {}


def normalize_function(
    fn: dict,
    tags: dict[str, str],
    region: str,
    collected_at: datetime,
) -> LambdaFunctionResourceRecord:
    resource_id = fn["FunctionName"]
    environment = normalize_environment(tags)

    warnings: list[str] = []
    if not tags:
        warnings.append("RESOURCE_HAS_NO_TAGS")

    last_modified = fn.get("LastModified")
    launched_at = None
    if isinstance(last_modified, str):
        try:
            launched_at = datetime.fromisoformat(last_modified.replace("+0000", "+00:00"))
        except ValueError:
            launched_at = None

    return LambdaFunctionResourceRecord(
        region=region,
        resource_id=resource_id,
        name=resource_id,
        environment=environment,
        instance_type=fn.get("Runtime", "unknown"),
        runtime=fn.get("Runtime"),
        timeout_seconds=fn.get("Timeout"),
        memory_size_mb=fn.get("MemorySize"),
        role_arn=fn.get("Role"),
        vpc_config_present=bool((fn.get("VpcConfig") or {}).get("VpcId")),
        state=str(fn.get("State", "unknown")).lower(),
        launched_at=launched_at,
        collected_at=collected_at,
        tags=tags,
        warnings=warnings,
    )


class LambdaCollector:
    def __init__(self, client_factory: AWSClientFactory, region: str):
        self.client_factory = client_factory
        self.region = region

    def collect(self) -> list[LambdaFunctionResourceRecord]:
        lambda_client = self.client_factory.client("lambda", region_name=self.region)
        paginator = lambda_client.get_paginator("list_functions")
        collected_at = datetime.now(timezone.utc)

        functions: list[LambdaFunctionResourceRecord] = []
        try:
            for page in paginator.paginate():
                for fn in page.get("Functions", []):
                    tags = _function_tags(lambda_client, fn.get("FunctionArn", ""))
                    functions.append(
                        normalize_function(
                            fn=fn,
                            tags=tags,
                            region=self.region,
                            collected_at=collected_at,
                        )
                    )
        except ClientError as error:
            error_code = error.response.get("Error", {}).get("Code", "UNKNOWN_AWS_ERROR")
            raise LambdaCollectionError(f"Lambda collection failed: {error_code}") from error

        return functions
