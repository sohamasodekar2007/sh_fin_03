"""
AWS cross-account session factory — lifted from blueprint section 9.2.

PLACEHOLDER: this code is real and will work once you:
  1. Create a read-only IAM role in a sandbox AWS account
     (see blueprint 7.2 "Security Controls" for the least-privilege policy).
  2. Set AWS_READ_ROLE_ARN and AWS_EXTERNAL_ID in apps/api/.env.example.
  3. Make sure the machine running this backend has AWS credentials capable
     of calling sts:AssumeRole on that role (e.g. via `aws configure` locally,
     or an instance profile in production) — CloudCare itself should never
     store long-lived customer AWS keys.
"""

import boto3

from apps.api.config import get_settings


def assumed_session(run_id: str) -> boto3.Session:
    settings = get_settings()
    if not settings.aws_read_role_arn or not settings.aws_external_id:
        raise RuntimeError(
            "AWS_READ_ROLE_ARN / AWS_EXTERNAL_ID are not set — fill them in "
            "apps/api/.env.example before calling assumed_session()."
        )

    sts = boto3.client("sts")
    response = sts.assume_role(
        RoleArn=settings.aws_read_role_arn,
        RoleSessionName=f"cloudcare-{run_id[:12]}",
        ExternalId=settings.aws_external_id,
        DurationSeconds=3600,
    )
    creds = response["Credentials"]
    return boto3.Session(
        aws_access_key_id=creds["AccessKeyId"],
        aws_secret_access_key=creds["SecretAccessKey"],
        aws_session_token=creds["SessionToken"],
    )
