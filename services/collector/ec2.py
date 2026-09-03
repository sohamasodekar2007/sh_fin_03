"""
EC2 + EBS inventory collector — real boto3 implementation.

Read-only: describe_instances / describe_volumes only. Requires the caller
to pass a boto3 Session already scoped to the customer's read-only role
(see packages/aws/aws_session.py::assumed_session).
"""

from __future__ import annotations

from typing import Any


def list_instances(session, region: str) -> list[dict[str, Any]]:
    ec2 = session.client("ec2", region_name=region)
    paginator = ec2.get_paginator("describe_instances")
    instances: list[dict[str, Any]] = []
    for page in paginator.paginate():
        for reservation in page["Reservations"]:
            instances.extend(reservation["Instances"])
    return instances


def list_unattached_volumes(session, region: str) -> list[dict[str, Any]]:
    ec2 = session.client("ec2", region_name=region)
    paginator = ec2.get_paginator("describe_volumes")
    volumes: list[dict[str, Any]] = []
    for page in paginator.paginate(Filters=[{"Name": "status", "Values": ["available"]}]):
        volumes.extend(page["Volumes"])
    return volumes
