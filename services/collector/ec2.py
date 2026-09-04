"""
EC2 inventory collector — PLACEHOLDER.

TODO: implement using boto3, per blueprint section 2.1 (Cloud Integration
layer). Example shape once implemented:

    def list_instances(session, region: str) -> list[dict]:
        ec2 = session.client("ec2", region_name=region)
        paginator = ec2.get_paginator("describe_instances")
        instances = []
        for page in paginator.paginate():
            for reservation in page["Reservations"]:
                instances.extend(reservation["Instances"])
        return instances

Normalize the raw boto3 response into the Resource schema
(app/models/schemas.py) before returning it to the orchestrator.
"""


def list_instances(session, region: str) -> list[dict]:
    raise NotImplementedError(
        "Wire this up to a real AWS sandbox account — see the module "
        "docstring for the boto3 implementation."
    )
