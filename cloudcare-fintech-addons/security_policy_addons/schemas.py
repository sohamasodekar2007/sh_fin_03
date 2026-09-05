from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Literal
from uuid import uuid4

from pydantic import BaseModel, Field

Severity = Literal["low", "medium", "high", "critical"]


class SecurityGroupRule(BaseModel):
    security_group_id: str
    port: int = Field(ge=0, le=65535)
    protocol: str
    cidr: str


class StorageResource(BaseModel):
    resource_id: str
    resource_type: Literal["ebs_volume", "rds_instance"]
    encrypted: bool


class S3BucketExposure(BaseModel):
    bucket: str
    public_access_block_enabled: bool
    acl_is_public: bool


class AccessKeySample(BaseModel):
    principal_name: str
    access_key_id: str
    age_days: int = Field(ge=0)


class SecurityPolicyFinding(BaseModel):
    """Audit-only, always — no field here could be misread as an approved
    action. Mirrors services/phase14/schemas.py's SecurityFinding shape
    deliberately, so merging these into that pipeline later (see
    ../MERGE_GUIDE.md) is a straight field-for-field mapping."""

    finding_id: str = Field(default_factory=lambda: str(uuid4()))
    rule_id: str
    severity: Severity
    resource_id: str
    resource_type: str
    summary: str
    evidence: dict[str, Any] = Field(default_factory=dict)
    rationale: str
    detected_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
