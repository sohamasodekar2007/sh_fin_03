from services.external_factors.aws_core_services import aws_core_services_payload


def test_aws_core_services_payload_covers_requested_services():
    payload = aws_core_services_payload()
    slugs = {service["slug"] for service in payload["services"]}

    assert slugs == {
        "ec2",
        "s3",
        "rds",
        "lambda",
        "vpc",
        "iam",
        "dynamodb",
        "cloudfront",
    }


def test_aws_core_services_keeps_dangerous_actions_out_of_executor_boundary():
    payload = aws_core_services_payload()
    excluded = set(payload["executor_role_boundaries"]["excluded"])

    assert "iam:*" in excluded
    assert "s3:DeleteBucket" in excluded
    assert "rds:DeleteDBInstance" in excluded
    assert "dynamodb:DeleteTable" in excluded
    assert "AmazonDynamoDBFullAccess_v2" in next(
        service for service in payload["services"] if service["slug"] == "dynamodb"
    )["full_access_policies"]
