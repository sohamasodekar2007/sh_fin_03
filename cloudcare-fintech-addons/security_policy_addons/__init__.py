"""New security posture checks beyond the main repo's existing IAM
wildcard-policy detection (services/phase14/iam_security_findings.py).
Same discipline as that module: audit-only, always — SecurityPolicyFinding
has no cost field and no execution field, so nothing here can enter the
real executable-proposal pipeline even by accident (see
services/phase14/schemas.py's docstring for why that separation is
structural in the main repo, a rule this package follows even though it
lives outside it).

Closes concrete gaps identified against the existing repo:
- Open security-group ingress on sensitive ports (nothing checked this).
- Unencrypted EBS/RDS storage (nothing checked this).
- Public S3 bucket exposure (nothing checked this).
- Stale IAM access keys — GovernanceUsersTable.tsx already *displays* key
  age against a 90-day threshold but never turns it into a finding.
"""

from .checks import check_open_security_groups, check_public_buckets, check_stale_access_keys, check_unencrypted_storage
from .schemas import AccessKeySample, S3BucketExposure, SecurityGroupRule, SecurityPolicyFinding, StorageResource

__all__ = [
    "check_open_security_groups",
    "check_unencrypted_storage",
    "check_public_buckets",
    "check_stale_access_keys",
    "SecurityGroupRule",
    "StorageResource",
    "S3BucketExposure",
    "AccessKeySample",
    "SecurityPolicyFinding",
]
