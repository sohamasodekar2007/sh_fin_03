from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field


class EC2ResourceRecord(BaseModel):
    schema_version: Literal["1.0"] = "1.0"

    provider: Literal["aws"] = "aws"
    resource_type: Literal["ec2_instance"] = "ec2_instance"

    region: str
    availability_zone: str | None = None

    resource_id: str
    name: str
    environment: str = "unknown"

    instance_type: str
    state: str

    launched_at: datetime | None = None
    collected_at: datetime

    private_ip: str | None = None
    public_ip: str | None = None

    vpc_id: str | None = None
    subnet_id: str | None = None

    tags: dict[str, str] = Field(default_factory=dict)
    warnings: list[str] = Field(default_factory=list)


class EBSVolumeResourceRecord(BaseModel):
    """Mirrors EC2ResourceRecord's shape closely enough that the FOCUS AWS
    mapper's _service_fields() (branches on resource_type == "ebs_volume")
    and the Analyzer's unattached-storage rule (keys on FOCUS
    ServiceCategory == "Storage") work unchanged — see
    services/focus/mappers/aws.py and services/analyzer/service.py."""

    schema_version: Literal["1.0"] = "1.0"

    provider: Literal["aws"] = "aws"
    resource_type: Literal["ebs_volume"] = "ebs_volume"

    region: str
    availability_zone: str | None = None

    resource_id: str
    name: str
    environment: str = "unknown"

    # "{size_gb}GB-{volume_type}", matching mock_provider's EBS shape so
    # both real and synthetic data render identically downstream.
    instance_type: str
    # boto3's raw Volume.State, lowercased: "available" (unattached) |
    # "in-use" | "creating" | "deleting" | "error".
    state: str

    launched_at: datetime | None = None
    collected_at: datetime

    tags: dict[str, str] = Field(default_factory=dict)
    warnings: list[str] = Field(default_factory=list)


class AzureVMResourceRecord(BaseModel):
    schema_version: Literal["1.0"] = "1.0"

    provider: Literal["azure"] = "azure"
    resource_type: Literal["azure_vm"] = "azure_vm"

    region: str  # Azure "location" (e.g. "eastus")
    resource_group: str | None = None

    resource_id: str  # full ARM resource ID — see vm_collector.py module docstring
    name: str
    environment: str = "unknown"

    # Named instance_type/state (not vm_size/power_state) deliberately: this
    # is what lets CloudSnapshot consumers built for EC2ResourceRecord
    # (analyzer rules, the dashboard) read Azure resources unchanged —
    # converging on one shape is the point of the FOCUS layer.
    instance_type: str
    state: str

    collected_at: datetime

    tags: dict[str, str] = Field(default_factory=dict)
    warnings: list[str] = Field(default_factory=list)


class AzureDiskResourceRecord(BaseModel):
    schema_version: Literal["1.0"] = "1.0"

    provider: Literal["azure"] = "azure"
    resource_type: Literal["azure_disk"] = "azure_disk"

    region: str
    resource_group: str | None = None

    resource_id: str
    name: str
    environment: str = "unknown"

    instance_type: str  # "{size_gb}GB-{sku_name}", mirrors mock_provider's EBS shape
    state: str  # disk_state, lowercased: "unattached" | "attached" | "reserved" | "unknown"

    collected_at: datetime

    tags: dict[str, str] = Field(default_factory=dict)
    warnings: list[str] = Field(default_factory=list)


class VPSResourceRecord(BaseModel):
    """One VM/container/host unit on a company-owned server. Carries the
    host's totals on every unit (not just once per host) because the FOCUS
    cost mapper (services/focus/mappers/vps.py) needs total_host_vcpu to
    compute each unit's allocated vCPU share, and a resource record is the
    only thing that survives into that mapper's input."""

    schema_version: Literal["1.0"] = "1.0"

    provider: Literal["vps"] = "vps"
    resource_type: Literal["vps_vm", "vps_container", "vps_host"]

    region: str = "on-premises"
    host: str

    # f"{host}:{unit_id}" is ResourceId's convention in the FOCUS mapper —
    # unit_id is the raw virsh/qm/lxc/docker identifier (or "host" for the
    # host-as-one-resource case), never truncated.
    unit_id: str
    resource_id: str
    name: str
    environment: str = "unknown"

    vcpu_count: float
    memory_mb: float
    disk_gb: float
    state: str

    host_total_vcpu: float
    host_total_memory_mb: float
    host_total_disk_gb: float

    collected_at: datetime

    tags: dict[str, str] = Field(default_factory=dict)
    warnings: list[str] = Field(default_factory=list)
