from __future__ import annotations

from datetime import datetime, timezone

from botocore.exceptions import ClientError

from packages.aws.session import AWSClientFactory
from packages.schemas.cloud_resource import DynamoDBTableResourceRecord
from services.collector.ec2_collector import normalize_environment


class DynamoDBCollectionError(Exception):
    """Raised when DynamoDB table inventory cannot be collected."""


def _table_tags(ddb_client, table_arn: str) -> dict[str, str]:
    try:
        resp = ddb_client.list_tags_of_resource(ResourceArn=table_arn)
        return {t["Key"]: t["Value"] for t in resp.get("Tags", [])}
    except ClientError:
        return {}


def normalize_table(
    description: dict,
    tags: dict[str, str],
    region: str,
    collected_at: datetime,
    point_in_time_recovery_enabled: bool | None = None,
) -> DynamoDBTableResourceRecord:
    resource_id = description["TableName"]
    environment = normalize_environment(tags)

    billing_mode = (
        description.get("BillingModeSummary", {}).get("BillingMode")
        or ("PROVISIONED" if description.get("ProvisionedThroughput") else "PAY_PER_REQUEST")
    )

    warnings: list[str] = []
    if not tags:
        warnings.append("RESOURCE_HAS_NO_TAGS")

    return DynamoDBTableResourceRecord(
        region=region,
        resource_id=resource_id,
        name=resource_id,
        environment=environment,
        instance_type=billing_mode,
        billing_mode=billing_mode,
        point_in_time_recovery_enabled=point_in_time_recovery_enabled,
        state=str(description.get("TableStatus", "unknown")).lower(),
        launched_at=description.get("CreationDateTime"),
        collected_at=collected_at,
        tags=tags,
        warnings=warnings,
    )


class DynamoDBCollector:
    def __init__(self, client_factory: AWSClientFactory, region: str):
        self.client_factory = client_factory
        self.region = region

    def collect(self) -> list[DynamoDBTableResourceRecord]:
        ddb = self.client_factory.client("dynamodb", region_name=self.region)
        paginator = ddb.get_paginator("list_tables")
        collected_at = datetime.now(timezone.utc)

        tables: list[DynamoDBTableResourceRecord] = []
        try:
            table_names: list[str] = []
            for page in paginator.paginate():
                table_names.extend(page.get("TableNames", []))

            for table_name in table_names:
                description = ddb.describe_table(TableName=table_name)["Table"]
                tags = _table_tags(ddb, description.get("TableArn", ""))
                pitr_enabled: bool | None = None
                try:
                    backup = ddb.describe_continuous_backups(TableName=table_name)
                    pitr_enabled = (
                        backup.get("ContinuousBackupsDescription", {})
                        .get("PointInTimeRecoveryDescription", {})
                        .get("PointInTimeRecoveryStatus")
                        == "ENABLED"
                    )
                except ClientError:
                    pitr_enabled = None
                tables.append(
                    normalize_table(
                        description=description,
                        tags=tags,
                        region=self.region,
                        collected_at=collected_at,
                        point_in_time_recovery_enabled=pitr_enabled,
                    )
                )
        except ClientError as error:
            error_code = error.response.get("Error", {}).get("Code", "UNKNOWN_AWS_ERROR")
            raise DynamoDBCollectionError(f"DynamoDB collection failed: {error_code}") from error

        return tables
