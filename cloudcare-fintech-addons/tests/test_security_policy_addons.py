from __future__ import annotations

from security_policy_addons import (
    AccessKeySample,
    S3BucketExposure,
    SecurityGroupRule,
    StorageResource,
    check_open_security_groups,
    check_public_buckets,
    check_stale_access_keys,
    check_unencrypted_storage,
)


def test_open_security_groups_flags_ssh_as_critical():
    rules = [SecurityGroupRule(security_group_id="sg-1", port=22, protocol="tcp", cidr="0.0.0.0/0")]
    findings = check_open_security_groups(rules)
    assert len(findings) == 1
    assert findings[0].severity == "critical"
    assert findings[0].resource_id == "sg-1"


def test_open_security_groups_flags_db_port_as_high_not_critical():
    rules = [SecurityGroupRule(security_group_id="sg-2", port=5432, protocol="tcp", cidr="0.0.0.0/0")]
    findings = check_open_security_groups(rules)
    assert findings[0].severity == "high"


def test_open_security_groups_ignores_non_sensitive_port():
    rules = [SecurityGroupRule(security_group_id="sg-3", port=8080, protocol="tcp", cidr="0.0.0.0/0")]
    assert check_open_security_groups(rules) == []


def test_open_security_groups_ignores_restricted_cidr():
    rules = [SecurityGroupRule(security_group_id="sg-4", port=22, protocol="tcp", cidr="10.0.0.0/16")]
    assert check_open_security_groups(rules) == []


def test_open_security_groups_flags_ipv6_open_cidr():
    rules = [SecurityGroupRule(security_group_id="sg-5", port=3389, protocol="tcp", cidr="::/0")]
    findings = check_open_security_groups(rules)
    assert len(findings) == 1
    assert findings[0].severity == "critical"


def test_unencrypted_storage_flags_only_unencrypted():
    resources = [
        StorageResource(resource_id="vol-1", resource_type="ebs_volume", encrypted=False),
        StorageResource(resource_id="vol-2", resource_type="ebs_volume", encrypted=True),
    ]
    findings = check_unencrypted_storage(resources)
    assert len(findings) == 1
    assert findings[0].resource_id == "vol-1"
    assert findings[0].severity == "medium"


def test_public_buckets_acl_public_is_critical():
    buckets = [S3BucketExposure(bucket="b1", public_access_block_enabled=True, acl_is_public=True)]
    findings = check_public_buckets(buckets)
    assert findings[0].severity == "critical"


def test_public_buckets_missing_block_is_high_not_critical():
    buckets = [S3BucketExposure(bucket="b2", public_access_block_enabled=False, acl_is_public=False)]
    findings = check_public_buckets(buckets)
    assert findings[0].severity == "high"


def test_public_buckets_fully_locked_down_produces_no_finding():
    buckets = [S3BucketExposure(bucket="b3", public_access_block_enabled=True, acl_is_public=False)]
    assert check_public_buckets(buckets) == []


def test_stale_access_keys_respects_threshold():
    keys = [
        AccessKeySample(principal_name="alice", access_key_id="AK1", age_days=45),
        AccessKeySample(principal_name="bob", access_key_id="AK2", age_days=120),
        AccessKeySample(principal_name="carol", access_key_id="AK3", age_days=200),
    ]
    findings = check_stale_access_keys(keys, max_age_days=90)
    ids = {f.resource_id: f.severity for f in findings}
    assert "AK1" not in ids
    assert ids["AK2"] == "medium"
    assert ids["AK3"] == "high"
