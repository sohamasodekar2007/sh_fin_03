"""Four pure, deterministic checks. Each takes a plain list of typed
samples (not a live boto3 call) so this is testable without AWS
credentials — see ../MERGE_GUIDE.md for wiring real
describe_security_groups / describe_volumes / get_bucket_policy_status /
list_access_keys calls in front of these, matching the pattern already
used by services/phase14/iam_security_findings.py."""

from __future__ import annotations

from .schemas import AccessKeySample, S3BucketExposure, SecurityGroupRule, SecurityPolicyFinding, StorageResource

_SENSITIVE_PORTS = {22: "SSH", 3389: "RDP", 3306: "MySQL", 5432: "PostgreSQL", 27017: "MongoDB", 6379: "Redis"}
_OPEN_CIDRS = {"0.0.0.0/0", "::/0"}
_HIGH_RISK_PORTS = {22, 3389}


def check_open_security_groups(rules: list[SecurityGroupRule]) -> list[SecurityPolicyFinding]:
    findings = []
    for rule in rules:
        if rule.cidr not in _OPEN_CIDRS or rule.port not in _SENSITIVE_PORTS:
            continue
        service = _SENSITIVE_PORTS[rule.port]
        severity = "critical" if rule.port in _HIGH_RISK_PORTS else "high"
        findings.append(
            SecurityPolicyFinding(
                rule_id="sg.open_ingress.v1",
                severity=severity,
                resource_id=rule.security_group_id,
                resource_type="security_group",
                summary=f"{service} ({rule.protocol}/{rule.port}) open to {rule.cidr}",
                evidence={"port": rule.port, "protocol": rule.protocol, "cidr": rule.cidr},
                rationale=(
                    f"Security group {rule.security_group_id} allows {service} from {rule.cidr} — unrestricted "
                    "internet access to a sensitive port, a common initial-access vector. Audit only; no rule "
                    "is modified by this check."
                ),
            )
        )
    return findings


def check_unencrypted_storage(resources: list[StorageResource]) -> list[SecurityPolicyFinding]:
    findings = []
    for resource in resources:
        if resource.encrypted:
            continue
        findings.append(
            SecurityPolicyFinding(
                rule_id="storage.unencrypted.v1",
                severity="medium",
                resource_id=resource.resource_id,
                resource_type=resource.resource_type,
                summary=f"{resource.resource_type} is not encrypted at rest",
                evidence={"encrypted": False},
                rationale=(
                    f"{resource.resource_id} ({resource.resource_type}) has no encryption at rest. Most engines "
                    "require encryption to be set at creation time, so this typically means a replacement or "
                    "migration, not an in-place fix — recommend only, this check never modifies the resource."
                ),
            )
        )
    return findings


def check_public_buckets(buckets: list[S3BucketExposure]) -> list[SecurityPolicyFinding]:
    findings = []
    for bucket in buckets:
        if not bucket.acl_is_public and bucket.public_access_block_enabled:
            continue
        if bucket.acl_is_public:
            severity, reason = "critical", "bucket ACL grants public access"
        else:
            severity, reason = "high", "S3 Block Public Access is not fully enabled"
        findings.append(
            SecurityPolicyFinding(
                rule_id="s3.public_exposure.v1",
                severity=severity,
                resource_id=bucket.bucket,
                resource_type="s3_bucket",
                summary=reason,
                evidence={
                    "public_access_block_enabled": bucket.public_access_block_enabled,
                    "acl_is_public": bucket.acl_is_public,
                },
                rationale=f"{bucket.bucket}: {reason}. Audit only — no bucket policy or ACL is changed by this check.",
            )
        )
    return findings


def check_stale_access_keys(keys: list[AccessKeySample], *, max_age_days: int = 90) -> list[SecurityPolicyFinding]:
    findings = []
    for key in keys:
        if key.age_days <= max_age_days:
            continue
        severity = "high" if key.age_days > max_age_days * 2 else "medium"
        findings.append(
            SecurityPolicyFinding(
                rule_id="iam.stale_access_key.v1",
                severity=severity,
                resource_id=key.access_key_id,
                resource_type="iam_access_key",
                summary=f"Access key is {key.age_days} days old (threshold {max_age_days})",
                evidence={"age_days": key.age_days, "principal_name": key.principal_name},
                rationale=(
                    f"Access key {key.access_key_id} for {key.principal_name} is {key.age_days} days old, past "
                    f"the {max_age_days}-day rotation threshold. Audit only — this check never rotates or "
                    "disables the key."
                ),
            )
        )
    return findings
