from __future__ import annotations

from unittest.mock import MagicMock

from services.phase14.iam_security_findings import IAMSecurityFindingsCollector, find_wildcard_grants


def test_find_wildcard_grants_flags_star_action():
    doc = {
        "Version": "2012-10-17",
        "Statement": [{"Effect": "Allow", "Action": "*", "Resource": "arn:aws:s3:::my-bucket"}],
    }
    reasons = find_wildcard_grants(doc)
    assert any("Action" in r for r in reasons)


def test_find_wildcard_grants_flags_star_resource():
    doc = {"Statement": [{"Effect": "Allow", "Action": "s3:GetObject", "Resource": "*"}]}
    reasons = find_wildcard_grants(doc)
    assert any("Resource" in r for r in reasons)


def test_find_wildcard_grants_flags_service_wildcard_action():
    doc = {"Statement": [{"Effect": "Allow", "Action": "s3:*", "Resource": "arn:aws:s3:::my-bucket"}]}
    reasons = find_wildcard_grants(doc)
    assert any("s3:*" in r for r in reasons)


def test_find_wildcard_grants_clean_policy_has_no_reasons():
    doc = {
        "Statement": [
            {"Effect": "Allow", "Action": ["s3:GetObject", "s3:PutObject"], "Resource": "arn:aws:s3:::my-bucket/*"}
        ]
    }
    assert find_wildcard_grants(doc) == []


def test_find_wildcard_grants_ignores_deny_statements():
    doc = {"Statement": [{"Effect": "Deny", "Action": "*", "Resource": "*"}]}
    assert find_wildcard_grants(doc) == []


def test_find_wildcard_grants_handles_single_statement_dict():
    doc = {"Statement": {"Effect": "Allow", "Action": "*", "Resource": "*"}}
    reasons = find_wildcard_grants(doc)
    assert len(reasons) == 2  # both action and resource flagged


def test_find_wildcard_grants_never_raises_on_malformed_document():
    assert find_wildcard_grants({}) == []
    assert find_wildcard_grants({"Statement": "not-a-list-or-dict"}) == []


def test_collector_flags_user_with_overly_broad_managed_policy():
    iam = MagicMock()
    paginator = MagicMock()
    paginator.paginate.return_value = [
        {
            "UserDetailList": [
                {
                    "UserName": "over-privileged",
                    "Arn": "arn:aws:iam::123:user/over-privileged",
                    "AttachedManagedPolicies": [{"PolicyName": "AdminAccess", "PolicyArn": "arn:aws:iam::aws:policy/AdminAccess"}],
                    "UserPolicyList": [],
                }
            ],
            "RoleDetailList": [],
        }
    ]
    iam.get_paginator.return_value = paginator
    iam.get_policy.return_value = {"Policy": {"DefaultVersionId": "v1"}}
    iam.get_policy_version.return_value = {
        "PolicyVersion": {"Document": {"Statement": [{"Effect": "Allow", "Action": "*", "Resource": "*"}]}}
    }

    factory = MagicMock()
    factory.client.return_value = iam
    collector = IAMSecurityFindingsCollector(client_factory=factory)

    findings = collector.collect()

    assert len(findings) == 1
    assert findings[0].principal_type == "user"
    assert findings[0].principal_name == "over-privileged"
    assert findings[0].policy_type == "managed"


def test_collector_flags_role_with_overly_broad_inline_policy():
    iam = MagicMock()
    paginator = MagicMock()
    paginator.paginate.return_value = [
        {
            "UserDetailList": [],
            "RoleDetailList": [
                {
                    "RoleName": "broad-role",
                    "Arn": "arn:aws:iam::123:role/broad-role",
                    "AttachedManagedPolicies": [],
                    "RolePolicyList": [
                        {"PolicyName": "InlineBroad", "PolicyDocument": {"Statement": [{"Effect": "Allow", "Action": "s3:*", "Resource": "*"}]}}
                    ],
                }
            ],
        }
    ]
    iam.get_paginator.return_value = paginator

    factory = MagicMock()
    factory.client.return_value = iam
    collector = IAMSecurityFindingsCollector(client_factory=factory)

    findings = collector.collect()

    assert len(findings) == 1
    assert findings[0].principal_type == "role"
    assert findings[0].policy_type == "inline"


def test_collector_no_findings_for_clean_policies():
    iam = MagicMock()
    paginator = MagicMock()
    paginator.paginate.return_value = [
        {
            "UserDetailList": [
                {
                    "UserName": "clean-user",
                    "Arn": "arn:aws:iam::123:user/clean-user",
                    "AttachedManagedPolicies": [],
                    "UserPolicyList": [
                        {"PolicyName": "Scoped", "PolicyDocument": {"Statement": [{"Effect": "Allow", "Action": "s3:GetObject", "Resource": "arn:aws:s3:::bucket/*"}]}}
                    ],
                }
            ],
            "RoleDetailList": [],
        }
    ]
    iam.get_paginator.return_value = paginator

    factory = MagicMock()
    factory.client.return_value = iam
    collector = IAMSecurityFindingsCollector(client_factory=factory)

    assert collector.collect() == []
