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


def assumed_session(run_id: str, role_arn: str | None = None, external_id: str | None = None) -> boto3.Session:
    """Assume a customer's read-only role. `role_arn`/`external_id` come
    from that customer's CloudAccount record; when omitted, falls back to
    the single dev-account role configured in .env (AWS_READ_ROLE_ARN /
    AWS_EXTERNAL_ID) for local testing without a full onboarding flow."""
    settings = get_settings()
    role_arn = role_arn or settings.aws_read_role_arn
    external_id = external_id or settings.aws_external_id
    if not role_arn or not external_id:
        raise RuntimeError(
            "No role_arn/external_id given and AWS_READ_ROLE_ARN / "
            "AWS_EXTERNAL_ID are not set — fill them in apps/api/.env "
            "before calling assumed_session()."
        )

    sts = boto3.client("sts")
    response = sts.assume_role(
        RoleArn=role_arn,
        RoleSessionName=f"cloudcare-{run_id[:12]}",
        ExternalId=external_id,
        DurationSeconds=3600,
    )
    creds = response["Credentials"]
    return boto3.Session(
        aws_access_key_id=creds["AccessKeyId"],
        aws_secret_access_key=creds["SecretAccessKey"],
        aws_session_token=creds["SessionToken"],
    )
