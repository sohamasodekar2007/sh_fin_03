"""
Azure managed disk collector — finds unattached disks (disk_state ==
"Unattached") so the unattached-storage analyzer rule works on Azure too,
the same way services/collector/ec2_collector.py's EBS volumes do for AWS.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from azure.core.exceptions import ClientAuthenticationError, HttpResponseError

from packages.azure.session import AzureClientFactory
from packages.schemas.cloud_resource import AzureDiskResourceRecord
from services.collector.azure.vm_collector import normalize_environment, resource_group_from_id


class AzureDiskCollectionError(Exception):
    """Raised when Azure managed disk inventory cannot be collected."""


def normalize_disk(
    disk: Any,
    collected_at: datetime,
) -> AzureDiskResourceRecord:
    tags = dict(getattr(disk, "tags", None) or {})

    resource_id = disk.id
    name = disk.name or resource_id
    environment = normalize_environment(tags)

    sku = getattr(disk, "sku", None)
    sku_name = getattr(sku, "name", None) or "unknown"
    size_gb = getattr(disk, "disk_size_gb", None) or 0
    disk_state = (getattr(disk, "disk_state", None) or "unknown").lower()

    warnings: list[str] = []
    if disk_state == "unattached":
        warnings.append("UNATTACHED_DISK")
    if not tags:
        warnings.append("RESOURCE_HAS_NO_TAGS")

    return AzureDiskResourceRecord(
        region=disk.location,
        resource_group=resource_group_from_id(resource_id),
        resource_id=resource_id,
        name=name,
        environment=environment,
        instance_type=f"{size_gb}GB-{sku_name}",
        state=disk_state,
        collected_at=collected_at,
        tags=tags,
        warnings=warnings,
    )


class AzureDiskCollector:
    def __init__(
        self,
        client_factory: AzureClientFactory,
    ) -> None:
        self.client_factory = client_factory

    def collect(self) -> list[AzureDiskResourceRecord]:
        client = self.client_factory.compute_client()
        collected_at = datetime.now(timezone.utc)
        resources: list[AzureDiskResourceRecord] = []

        try:
            for disk in client.disks.list():
                resources.append(normalize_disk(disk, collected_at))
        except ClientAuthenticationError as error:
            raise AzureDiskCollectionError(
                f"Azure disk collection failed: authentication error ({error})"
            ) from error
        except HttpResponseError as error:
            error_code = error.error.code if error.error else "UNKNOWN_AZURE_ERROR"
            raise AzureDiskCollectionError(
                f"Azure disk collection failed: {error_code}"
            ) from error

        return resources

    def collect_unattached(self) -> list[AzureDiskResourceRecord]:
        return [d for d in self.collect() if d.state == "unattached"]
