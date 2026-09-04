from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone
from typing import Any


AWS_CORE_SERVICES: list[dict[str, Any]] = [
    {
        "service": "Amazon EC2",
        "slug": "ec2",
        "resource_types": ["ec2_instance", "ebs_volume"],
        "purpose": "Virtual servers and attached block storage used for application compute capacity.",
        "inventory_status": "implemented",
        "collector_actions": [
            "ec2:DescribeInstances",
            "ec2:DescribeVolumes",
            "ec2:DescribeTags",
            "ec2:DescribeInstanceAttribute",
            "autoscaling:DescribeAutoScalingGroups",
            "elasticloadbalancing:DescribeTargetHealth",
        ],
        "read_only_policies": ["AmazonEC2ReadOnlyAccess", "CloudWatchReadOnlyAccess"],
        "full_access_policies": ["AmazonEC2FullAccess"],
        "approved_executor_actions": [
            "ec2:StartInstances",
            "ec2:StopInstances",
            "ec2:ModifyInstanceAttribute",
            "ec2:CreateTags",
            "autoscaling:UpdateAutoScalingGroup",
        ],
        "blocked_executor_actions": ["ec2:TerminateInstances", "ec2:DeleteVpc", "ec2:DeleteSubnet"],
        "rules": [
            "Flag idle instances only with real CPU/network evidence.",
            "Flag over-provisioned instances only when metric sample count is sufficient.",
            "Do not stop instances in Auto Scaling groups without an ASG capacity proposal.",
            "Require human approval and the configured allowlist tag before any live mutation.",
        ],
        "risk_notes": "Stopping is reversible; termination and VPC deletion are intentionally excluded.",
    },
    {
        "service": "Amazon S3",
        "slug": "s3",
        "resource_types": ["s3_bucket"],
        "purpose": "Durable object storage for files, backups, logs, exports, and static assets.",
        "inventory_status": "implemented",
        "collector_actions": [
            "s3:ListAllMyBuckets",
            "s3:GetBucketLocation",
            "s3:GetBucketTagging",
            "s3:GetBucketLifecycleConfiguration",
            "cloudwatch:GetMetricStatistics",
        ],
        "read_only_policies": ["AmazonS3ReadOnlyAccess"],
        "full_access_policies": ["AmazonS3FullAccess"],
        "approved_executor_actions": ["s3:PutLifecycleConfiguration", "s3:PutBucketTagging"],
        "blocked_executor_actions": ["s3:DeleteBucket", "s3:DeleteObject", "s3:PutBucketPolicy"],
        "rules": [
            "Recommend storage-class lifecycle only when lifecycle configuration and size trend support it.",
            "Never infer object contents or read object data from inventory collection.",
            "Treat missing tags as a governance issue, not a deletion candidate.",
        ],
        "risk_notes": "Bucket and object deletion are destructive and should stay outside automatic execution.",
    },
    {
        "service": "Amazon RDS",
        "slug": "rds",
        "resource_types": ["rds_instance"],
        "purpose": "Managed relational databases such as PostgreSQL, MySQL, MariaDB, Oracle, and SQL Server.",
        "inventory_status": "implemented",
        "collector_actions": [
            "rds:DescribeDBInstances",
            "rds:ListTagsForResource",
            "cloudwatch:GetMetricStatistics",
        ],
        "read_only_policies": ["AmazonRDSReadOnlyAccess"],
        "full_access_policies": ["AmazonRDSFullAccess"],
        "approved_executor_actions": ["rds:StartDBInstance", "rds:StopDBInstance", "rds:ModifyDBInstance", "rds:AddTagsToResource"],
        "blocked_executor_actions": ["rds:DeleteDBInstance", "rds:DeleteDBCluster", "rds:ModifyDBClusterSnapshotAttribute"],
        "rules": [
            "Show Multi-AZ and deletion-protection context before any stop/resize decision.",
            "Do not propose database stop without connection and CPU evidence.",
            "Require a final snapshot or rollback plan for any future destructive database action.",
        ],
        "risk_notes": "Database changes can create downtime; all RDS mutations must remain human-approved.",
    },
    {
        "service": "AWS Lambda",
        "slug": "lambda",
        "resource_types": ["lambda_function"],
        "purpose": "Serverless functions that execute code in response to events.",
        "inventory_status": "implemented",
        "collector_actions": ["lambda:ListFunctions", "lambda:ListTags", "cloudwatch:GetMetricData"],
        "read_only_policies": ["AWSLambda_ReadOnlyAccess"],
        "full_access_policies": ["AWSLambda_FullAccess"],
        "approved_executor_actions": ["lambda:UpdateFunctionConfiguration", "lambda:PutFunctionConcurrency", "lambda:TagResource"],
        "blocked_executor_actions": ["lambda:DeleteFunction", "lambda:RemovePermission"],
        "rules": [
            "Surface runtime, state, tags, and cost context before concurrency or memory changes.",
            "Use scoped iam:PassRole only for approved Lambda execution roles when creation/update support is added.",
            "Do not delete functions automatically.",
        ],
        "risk_notes": "Function updates can break production event flows; deletion is excluded.",
    },
    {
        "service": "Amazon VPC",
        "slug": "vpc",
        "resource_types": ["vpc"],
        "purpose": "Isolated networking boundary for subnets, routing, security groups, gateways, and endpoints.",
        "inventory_status": "implemented",
        "collector_actions": ["ec2:DescribeVpcs", "ec2:DescribeSubnets", "ec2:DescribeRouteTables", "ec2:DescribeSecurityGroups"],
        "read_only_policies": ["AmazonVPCReadOnlyAccess", "AmazonEC2ReadOnlyAccess"],
        "full_access_policies": ["AmazonVPCFullAccess"],
        "approved_executor_actions": ["ec2:CreateTags"],
        "blocked_executor_actions": [
            "ec2:DeleteVpc",
            "ec2:DeleteSubnet",
            "ec2:DeleteRouteTable",
            "ec2:RevokeSecurityGroupIngress",
        ],
        "rules": [
            "Use VPC inventory as dependency context for compute, Lambda, RDS, and CloudFront origins.",
            "Treat security-group and routing changes as security-reviewed actions.",
            "Never delete network primitives from cost automation.",
        ],
        "risk_notes": "Networking changes can take applications offline; only tagging is allowed in this feature layer.",
    },
    {
        "service": "AWS IAM",
        "slug": "iam",
        "resource_types": ["iam_user"],
        "purpose": "Identity, access, roles, policies, account posture, and audit visibility.",
        "inventory_status": "implemented",
        "collector_actions": [
            "iam:GetAccountSummary",
            "iam:ListAccountAliases",
            "iam:GetAccountPasswordPolicy",
            "iam:GetAccountAuthorizationDetails",
            "iam:ListAccessKeys",
            "iam:ListUserTags",
            "cloudtrail:LookupEvents",
        ],
        "read_only_policies": ["IAMReadOnlyAccess", "AWSCloudTrail_ReadOnlyAccess"],
        "full_access_policies": ["IAMFullAccess"],
        "approved_executor_actions": [],
        "blocked_executor_actions": [
            "iam:PutUserPolicy",
            "iam:PutRolePolicy",
            "iam:AttachRolePolicy",
            "iam:CreateAccessKey",
            "iam:DeleteUser",
        ],
        "rules": [
            "Detect broad admin policies, stale access keys, missing MFA posture, and creator attribution from CloudTrail.",
            "Do not let the application grant IAM permissions to itself.",
            "Use separate read and executor roles with ExternalId for customer accounts.",
        ],
        "risk_notes": "IAM write access is privilege escalation territory and should stay admin-only.",
    },
    {
        "service": "Amazon DynamoDB",
        "slug": "dynamodb",
        "resource_types": ["dynamodb_table"],
        "purpose": "Managed NoSQL tables for high-throughput, low-latency key-value and document workloads.",
        "inventory_status": "implemented",
        "collector_actions": ["dynamodb:ListTables", "dynamodb:DescribeTable", "dynamodb:ListTagsOfResource"],
        "read_only_policies": ["AmazonDynamoDBReadOnlyAccess"],
        "full_access_policies": ["AmazonDynamoDBFullAccess_v2"],
        "approved_executor_actions": ["dynamodb:UpdateTable", "dynamodb:UpdateContinuousBackups", "dynamodb:TagResource"],
        "blocked_executor_actions": ["dynamodb:DeleteTable", "dynamodb:DeleteBackup", "dynamodb:UpdateGlobalTable"],
        "rules": [
            "Surface billing mode, table status, tags, and backup posture before changes.",
            "Prefer capacity/billing optimization over destructive table actions.",
            "Use the current AmazonDynamoDBFullAccess_v2 managed policy name for full-access setups.",
        ],
        "risk_notes": "Table deletion is data loss and is excluded from executor automation.",
    },
    {
        "service": "Amazon CloudFront",
        "slug": "cloudfront",
        "resource_types": ["cloudfront_distribution"],
        "purpose": "Global CDN for static and dynamic web content distribution.",
        "inventory_status": "implemented",
        "collector_actions": ["cloudfront:ListDistributions", "cloudfront:ListTagsForResource", "cloudfront:GetDistributionConfig"],
        "read_only_policies": ["CloudFrontReadOnlyAccess"],
        "full_access_policies": ["CloudFrontFullAccess"],
        "approved_executor_actions": ["cloudfront:UpdateDistribution", "cloudfront:CreateInvalidation"],
        "blocked_executor_actions": ["cloudfront:DeleteDistribution", "cloudfront:DeleteFunction"],
        "rules": [
            "Show enabled state, price class, aliases, and origin context before updates.",
            "Require ETag-aware update flow for distribution config changes.",
            "Do not delete distributions automatically.",
        ],
        "risk_notes": "Distribution updates can affect global traffic; all changes need human approval.",
    },
]


DISCOVERY_ROLE_RECOMMENDATIONS = [
    "ViewOnlyAccess",
    "CloudWatchReadOnlyAccess",
    "AWSBillingReadOnlyAccess",
    "ComputeOptimizerReadOnlyAccess",
    "CostOptimizationHubReadOnlyAccess",
    "ResourceGroupsandTagEditorReadOnlyAccess",
    "AWSCloudTrail_ReadOnlyAccess",
]


EXECUTOR_ROLE_BOUNDARIES = {
    "allowed_pattern": "Only explicitly listed start/stop/resize/tag/capacity/configuration actions after approval.",
    "excluded": [
        "iam:*",
        "organizations:*",
        "account:*",
        "s3:DeleteBucket",
        "s3:DeleteObject",
        "rds:DeleteDBInstance",
        "dynamodb:DeleteTable",
        "cloudtrail:StopLogging",
        "cloudtrail:DeleteTrail",
    ],
    "required_gates": [
        "EXECUTION_ENABLED=true",
        "EXECUTION_MODE=live for real AWS mutation",
        "proposal status is approved",
        "current live tags pass policy engine",
        "resource has the configured execution allowlist tag",
        "executor writes an audit log for success, no-op, refusal, or failure",
    ],
}


def aws_core_services_payload() -> dict[str, Any]:
    """Return a detached service/rule/policy plan for the dashboard.

    This module intentionally has no AWS clients and performs no mutations.
    It is an external-factor knowledge layer that the UI can remove without
    touching collectors, analyzers, or the executor.
    """

    services = deepcopy(AWS_CORE_SERVICES)
    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "source": "external_factor.aws_core_services",
        "scope": "EC2, S3, RDS, Lambda, VPC, IAM, DynamoDB, CloudFront",
        "services": services,
        "discovery_role_recommendations": DISCOVERY_ROLE_RECOMMENDATIONS,
        "executor_role_boundaries": deepcopy(EXECUTOR_ROLE_BOUNDARIES),
        "notes": [
            "Discovery and executor roles stay separate.",
            "Full-access managed policies are documented for admin setup, not attached to the runtime automatically.",
            "Delete actions are explicitly blocked unless a future feature adds service-specific backup, approval, and rollback controls.",
        ],
    }
