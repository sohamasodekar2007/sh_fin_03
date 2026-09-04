"""
IAM & Governance contracts — "who can do what, and who created what."
Deliberately separate from packages/schemas/cloud_resource.py's Resource
records: this is account-wide identity/access structure plus a CloudTrail
audit trail, not a per-resource inventory line, so it doesn't try to share
a shape with ResourceItem.
"""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field


class AccountOverview(BaseModel):
    account_id: str
    alias: str | None = None
    # None (not False) when get_account_summary itself couldn't be read —
    # "unknown" must never render as "MFA disabled," a much stronger and
    # potentially false claim.
    root_mfa_enabled: bool | None = None
    root_access_keys_present: bool | None = None
    password_policy_configured: bool | None = None


class IAMPolicyRef(BaseModel):
    name: str
    arn: str | None = None
    type: Literal["managed", "inline"]
    # Only ever populated for inline policies — a managed policy's document
    # would need a second GetPolicyVersion call per policy, multiplying
    # request count for marginal value when the ARN already identifies it.
    document: dict | None = None


class IAMUserDetail(BaseModel):
    user_name: str
    arn: str
    created_at: datetime | None = None
    groups: list[str] = Field(default_factory=list)
    policies: list[IAMPolicyRef] = Field(default_factory=list)
    # None when no active access key exists at all — distinct from "0 days
    # old," which would be a real, very-fresh key.
    access_key_age_days: int | None = None


class ResourceCreator(BaseModel):
    resource_id: str
    event_name: str
    principal_arn: str | None = None
    principal_name: str | None = None
    event_time: datetime


class IAMGovernanceOverview(BaseModel):
    account: AccountOverview
    users: list[IAMUserDetail] = Field(default_factory=list)
    resource_creators: list[ResourceCreator] = Field(default_factory=list)
    # Always stated explicitly, never left implicit — CloudTrail LookupEvents
    # only ever covers this many trailing days without a configured
    # multi-year trail, so a resource older than this shows "creator
    # unknown," not a guess.
    resource_creators_lookback_days: int = 90
    # Set when a section couldn't be collected at all (e.g. CloudTrail
    # access denied) so the frontend can say why, not just show empty.
    errors: dict[str, str] = Field(default_factory=dict)
