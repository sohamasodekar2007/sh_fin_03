"""
Azure VM inventory collector — the AzureVMCollector analog of
services/collector/ec2_collector.py:EC2Collector.

Azure resource IDs are long ARM paths
(/subscriptions/{sub}/resourceGroups/{rg}/providers/Microsoft.Compute/virtualMachines/{name}),
not short IDs like "i-0abc...". Never truncate or reformat resource_id —
it's the join key back to the `resource_metrics` collection
(services/collector/azure/metrics_collector.py).
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from azure.core.exceptions import ClientAuthenticationError, HttpResponseError

from packages.azure.session import AzureClientFactory
from packages.schemas.cloud_resource import AzureVMResourceRecord

_ENVIRONMENT_ALIASES = {
    "dev": "development", "development": "development",
    "stage": "staging", "stg": "staging", "staging": "staging",
    "prod": "production", "production": "production",
}


class AzureVMCollectionError(Exception):
    """Raised when Azure VM inventory cannot be collected."""


def find_tag(tags: dict[str, str], required_key: str) -> str | None:
    for key, value in tags.items():
        if key.lower() == required_key.lower():
            return value
    return None


def normalize_environment(tags: dict[str, str]) -> str:
    raw_environment = find_tag(tags, "Environment")

    if not raw_environment:
        return "unknown"

    normalized = raw_environment.strip().lower()

    return _ENVIRONMENT_ALIASES.get(normalized, "unknown")


def resource_group_from_id(resource_id: str) -> str | None:
    """Parses the resourceGroups segment out of a full ARM resource ID.
    Only used to populate a display field — resource_id itself is never
    truncated or reconstructed from this."""
    parts = resource_id.split("/")
    for index, part in enumerate(parts):
        if part.lower() == "resourcegroups" and index + 1 < len(parts):
            return parts[index + 1]
    return None


def power_state_from_instance_view(vm: Any) -> str:
    """Azure reports power state as a status code like "PowerState/running"
    inside instance_view.statuses, populated when the VM list call is made
    with status_only="true" (see AzureVMCollector.collect)."""
    instance_view = getattr(vm, "instance_view", None)
    statuses = getattr(instance_view, "statuses", None) if instance_view else None

    for status in statuses or []:
        code = getattr(status, "code", "") or ""
        if code.startswith("PowerState/"):
            return code.split("/", 1)[1]

    return "unknown"


def normalize_vm(
    vm: Any,
    collected_at: datetime,
) -> AzureVMResourceRecord:
    tags = dict(getattr(vm, "tags", None) or {})

    resource_id = vm.id
    name = vm.name or resource_id
    environment = normalize_environment(tags)

    hardware_profile = getattr(vm, "hardware_profile", None)
    vm_size = getattr(hardware_profile, "vm_size", None) or "unknown"

    power_state = power_state_from_instance_view(vm)

    warnings: list[str] = []

    if not tags:
        warnings.append("RESOURCE_HAS_NO_TAGS")

    if environment == "unknown":
        warnings.append("ENVIRONMENT_TAG_MISSING_OR_INVALID")

    return AzureVMResourceRecord(
        region=vm.location,
        resource_group=resource_group_from_id(resource_id),
        resource_id=resource_id,
        name=name,
        environment=environment,
        instance_type=vm_size,
        state=power_state,
        collected_at=collected_at,
        tags=tags,
        warnings=warnings,
    )


class AzureVMCollector:
    def __init__(
        self,
        client_factory: AzureClientFactory,
    ) -> None:
        self.client_factory = client_factory

    def collect(self) -> list[AzureVMResourceRecord]:
        client = self.client_factory.compute_client()
        collected_at = datetime.now(timezone.utc)
        resources: list[AzureVMResourceRecord] = []

        try:
            # status_only="true" includes instance_view.statuses (power
            # state) inline, avoiding one instance_view() call per VM.
            for vm in client.virtual_machines.list_all(status_only="true"):
                resources.append(normalize_vm(vm, collected_at))
        except ClientAuthenticationError as error:
            raise AzureVMCollectionError(
                f"Azure VM collection failed: authentication error ({error})"
            ) from error
        except HttpResponseError as error:
            error_code = error.error.code if error.error else "UNKNOWN_AZURE_ERROR"
            raise AzureVMCollectionError(
                f"Azure VM collection failed: {error_code}"
            ) from error

        return resources
