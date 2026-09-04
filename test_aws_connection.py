import os
from pathlib import Path

import boto3
from botocore.exceptions import ClientError
from dotenv import load_dotenv


ENV_PATH = Path(__file__).resolve().parent / "backend" / ".env"

load_dotenv(ENV_PATH)

PROFILE = os.getenv("AWS_PROFILE", "cloudcare-bootstrap")
REGION = os.getenv("AWS_REGION", "ap-south-1")

ROLE_ARN = os.getenv("AWS_ROLE_ARN")
EXTERNAL_ID = os.getenv("AWS_EXTERNAL_ID")


def main():
    if not ROLE_ARN or not EXTERNAL_ID:
        print("Missing AWS_ROLE_ARN or AWS_EXTERNAL_ID in backend/.env")
        return

    try:
        base_session = boto3.Session(
            profile_name=PROFILE,
            region_name=REGION,
        )

        base_sts = base_session.client("sts")

        base_identity = base_sts.get_caller_identity()

        print("Base identity connected:")
        print(base_identity["Arn"])

        assumed_role = base_sts.assume_role(
            RoleArn=ROLE_ARN,
            RoleSessionName="cloudcare-python-test",
            ExternalId=EXTERNAL_ID,
            DurationSeconds=3600,
        )

        credentials = assumed_role["Credentials"]

        cloudcare_session = boto3.Session(
            aws_access_key_id=credentials["AccessKeyId"],
            aws_secret_access_key=credentials["SecretAccessKey"],
            aws_session_token=credentials["SessionToken"],
            region_name=REGION,
        )

        assumed_sts = cloudcare_session.client("sts")

        assumed_identity = assumed_sts.get_caller_identity()

        print("\nRole assumed successfully:")
        print(assumed_identity["Arn"])

        ec2 = cloudcare_session.client(
            "ec2",
            region_name=REGION,
        )

        paginator = ec2.get_paginator(
            "describe_instances"
        )

        instance_count = 0

        for page in paginator.paginate():
            for reservation in page.get("Reservations", []):
                instance_count += len(
                    reservation.get("Instances", [])
                )

        print("\nConnection successful.")
        print(f"EC2 instances found: {instance_count}")

    except ClientError as error:
        code = error.response.get(
            "Error",
            {},
        ).get(
            "Code",
            "UNKNOWN_ERROR",
        )

        print(f"AWS error: {code}")


if __name__ == "__main__":
    main()
