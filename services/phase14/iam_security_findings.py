"""
IAM as a read-only audit surface — never an action target. Self-contained
(does not import services/collector/iam_governance_collector.py, even
though that module already fetches inline policy documents for users, to
keep this package deletable as a single unit without touching another
folder's dependency graph) — one get_account_authorization_details call
covering both users and roles (the doc calls out roles specifically:
"a role that only ever calls one or two specific S3 actions"), plus one
get_policy/get_policy_version pair per attached managed policy, which
get_account_authorization_details does not inline for you the way it does
for inline policies.

The IAM permissions this needs are themselves strictly read-only
(iam:List*, iam:Get*) — this module is structurally incapable of writing
to any IAM policy, not just conventionally discouraged from it.
"""

from __future__ import annotations

import logging
from typing import Any

from botocore.exceptions import ClientError

from services.phase14.schemas import SecurityFinding

logger = logging.getLogger(__name__)

# Broad-enough wildcard actions worth flagging even without a literal "*" —
# a real, common over-permissioning pattern (e.g. "s3:*" on a role that
# only ever needs GetObject/PutObject).
_WILDCARD_SERVICE_ACTION_SUFFIX = ":*"


class IAMSecurityFindingsError(Exception):
    """Raised when the IAM security review cannot be run at all."""


def find_wildcard_grants(policy_document: dict[str, Any]) -> list[str]:
    """Pure function, no AWS calls — returns a list of human-readable
    reasons this policy document was flagged, or an empty list if clean.
    Never raises on a malformed document; treats anything it can't parse
    as not-flaggable rather than guessing."""
    reasons: list[str] = []
    statements = policy_document.get("Statement", [])
    if isinstance(statements, dict):
        statements = [statements]

    for statement in statements:
        if not isinstance(statement, dict) or statement.get("Effect") != "Allow":
            continue

        actions = statement.get("Action", [])
        if isinstance(actions, str):
            actions = [actions]
        resources = statement.get("Resource", [])
        if isinstance(resources, str):
            resources = [resources]

        if "*" in actions:
            reasons.append('Grants "Action": "*" — every action on every matched resource.')
        else:
            wildcard_actions = [a for a in actions if isinstance(a, str) and a.endswith(_WILDCARD_SERVICE_ACTION_SUFFIX)]
            for action in wildcard_actions:
                reasons.append(f'Grants "{action}" — every action in that service, not a specific one.')

        if "*" in resources:
            reasons.append('Grants access to "Resource": "*" — every resource in the account, not a scoped set.')

    return reasons


def _policy_document(iam_client: Any, policy_arn: str) -> dict[str, Any] | None:
    try:
        policy = iam_client.get_policy(PolicyArn=policy_arn)["Policy"]
        version_id = policy["DefaultVersionId"]
        version = iam_client.get_policy_version(PolicyArn=policy_arn, VersionId=version_id)
        return version["PolicyVersion"]["Document"]
    except ClientError as error:
        logger.info("phase14.iam_security_findings: could not fetch managed policy %s: %s", policy_arn, error)
        return None


def _findings_for_principal(
    iam_client: Any,
    principal_type: str,
    name: str,
    arn: str,
    attached_managed_policies: list[dict[str, Any]],
    inline_policies: list[dict[str, Any]],
    managed_name_key: str,
    inline_name_key: str,
) -> list[SecurityFinding]:
    findings: list[SecurityFinding] = []

    for managed in attached_managed_policies:
        document = _policy_document(iam_client, managed["PolicyArn"])
        if document is None:
            continue
        reasons = find_wildcard_grants(document)
        if reasons:
            findings.append(
                SecurityFinding(
                    rule_id="iam.overly_broad_policy.v1",
                    severity="high",
                    principal_type=principal_type,  # type: ignore[arg-type]
                    principal_name=name,
                    principal_arn=arn,
                    policy_name=managed[managed_name_key],
                    policy_type="managed",
                    summary=f"{principal_type.capitalize()} '{name}' has an overly broad managed policy attached.",
                    evidence={"reasons": reasons, "policy_arn": managed["PolicyArn"]},
                )
            )

    for inline in inline_policies:
        document = inline.get("PolicyDocument")
        if not document:
            continue
        reasons = find_wildcard_grants(document)
        if reasons:
            findings.append(
                SecurityFinding(
                    rule_id="iam.overly_broad_policy.v1",
                    severity="high",
                    principal_type=principal_type,  # type: ignore[arg-type]
                    principal_name=name,
                    principal_arn=arn,
                    policy_name=inline[inline_name_key],
                    policy_type="inline",
                    summary=f"{principal_type.capitalize()} '{name}' has an overly broad inline policy.",
                    evidence={"reasons": reasons},
                )
            )

    return findings


class IAMSecurityFindingsCollector:
    def __init__(self, client_factory: Any):
        self.client_factory = client_factory

    def collect(self) -> list[SecurityFinding]:
        iam = self.client_factory.client("iam", region_name="us-east-1")

        try:
            paginator = iam.get_paginator("get_account_authorization_details")
            users: list[dict[str, Any]] = []
            roles: list[dict[str, Any]] = []
            for page in paginator.paginate(Filter=["User", "Role"]):
                users.extend(page.get("UserDetailList", []))
                roles.extend(page.get("RoleDetailList", []))
        except ClientError as error:
            error_code = error.response.get("Error", {}).get("Code", "UNKNOWN_AWS_ERROR")
            raise IAMSecurityFindingsError(f"IAM security review failed: {error_code}") from error

        findings: list[SecurityFinding] = []

        for user in users:
            findings.extend(
                _findings_for_principal(
                    iam,
                    "user",
                    user["UserName"],
                    user["Arn"],
                    user.get("AttachedManagedPolicies", []),
                    user.get("UserPolicyList", []),
                    managed_name_key="PolicyName",
                    inline_name_key="PolicyName",
                )
            )

        for role in roles:
            findings.extend(
                _findings_for_principal(
                    iam,
                    "role",
                    role["RoleName"],
                    role["Arn"],
                    role.get("AttachedManagedPolicies", []),
                    role.get("RolePolicyList", []),
                    managed_name_key="PolicyName",
                    inline_name_key="PolicyName",
                )
            )

        return findings
