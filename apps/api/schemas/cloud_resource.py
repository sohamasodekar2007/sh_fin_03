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
