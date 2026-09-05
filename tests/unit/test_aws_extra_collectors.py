from __future__ import annotations

from datetime import datetime, timezone

from services.collector.cloudfront_collector import normalize_distribution
from services.collector.dynamodb_collector import normalize_table
from services.collector.ec2_collector import normalize_security_group, normalize_vpc
from services.collector.iam_collector import normalize_user
from services.collector.lambda_collector import normalize_function
from services.collector.rds_collector import normalize_db_instance
from services.collector.s3_collector import normalize_bucket


def _now():
    return datetime.now(timezone.utc)


def test_normalize_vpc():
    vpc = {
        "VpcId": "vpc-test123",
        "CidrBlock": "10.0.0.0/16",
        "State": "available",
        "Tags": [{"Key": "Name", "Value": "main-vpc"}, {"Key": "Environment", "Value": "prod"}],
    }
    result = normalize_vpc(vpc, region="ap-south-1", collected_at=_now())
    assert result.resource_type == "vpc"
    assert result.resource_id == "vpc-test123"
    assert result.instance_type == "10.0.0.0/16"
    assert result.state == "available"
    assert result.environment == "production"


def test_normalize_security_group_keeps_open_ingress_rules():
    group = {
        "GroupId": "sg-123",
        "GroupName": "db-access",
        "VpcId": "vpc-123",
        "IpPermissions": [
            {
                "IpProtocol": "tcp",
                "FromPort": 5432,
                "ToPort": 5432,
                "IpRanges": [{"CidrIp": "0.0.0.0/0"}],
            }
        ],
    }
    result = normalize_security_group(group, region="ap-south-1", collected_at=_now())

    assert result.resource_type == "security_group"
    assert result.resource_id == "sg-123"
    assert result.vpc_id == "vpc-123"
    assert result.ingress_rules[0]["from_port"] == 5432
    assert "HAS_INTERNET_INGRESS" in result.warnings


def test_normalize_bucket_flags_missing_tags():
    bucket = {"Name": "my-test-bucket", "CreationDate": _now()}
    result = normalize_bucket(bucket, tags={}, region="us-east-1", collected_at=_now())
    assert result.resource_type == "s3_bucket"
    assert result.resource_id == "my-test-bucket"
    assert "RESOURCE_HAS_NO_TAGS" in result.warnings


def test_normalize_db_instance_flags_single_az():
    instance = {
        "DBInstanceIdentifier": "prod-db-1",
        "DBInstanceClass": "db.t3.micro",
        "DBInstanceStatus": "available",
        "MultiAZ": False,
        "TagList": [{"Key": "Environment", "Value": "prod"}],
    }
    result = normalize_db_instance(instance, region="ap-south-1", collected_at=_now())
    assert result.resource_type == "rds_instance"
    assert result.instance_type == "db.t3.micro"
    assert result.state == "available"
    assert "SINGLE_AZ_NO_REDUNDANCY" in result.warnings


def test_normalize_db_instance_multi_az_no_redundancy_warning():
    instance = {
        "DBInstanceIdentifier": "prod-db-2",
        "DBInstanceClass": "db.t3.micro",
        "DBInstanceStatus": "available",
        "MultiAZ": True,
        "TagList": [{"Key": "Environment", "Value": "prod"}],
    }
    result = normalize_db_instance(instance, region="ap-south-1", collected_at=_now())
    assert "SINGLE_AZ_NO_REDUNDANCY" not in result.warnings


def test_normalize_function():
    fn = {
        "FunctionName": "my-handler",
        "Runtime": "python3.12",
        "State": "Active",
        "LastModified": "2026-01-01T10:00:00.000+0000",
    }
    result = normalize_function(fn, tags={"Environment": "dev"}, region="ap-south-1", collected_at=_now())
    assert result.resource_type == "lambda_function"
    assert result.instance_type == "python3.12"
    assert result.state == "active"
    assert result.environment == "development"


def test_normalize_table_infers_pay_per_request_billing_mode():
    description = {
        "TableName": "sessions",
        "TableStatus": "ACTIVE",
        "BillingModeSummary": {"BillingMode": "PAY_PER_REQUEST"},
        "CreationDateTime": _now(),
    }
    result = normalize_table(description, tags={}, region="ap-south-1", collected_at=_now())
    assert result.resource_type == "dynamodb_table"
    assert result.instance_type == "PAY_PER_REQUEST"
    assert result.state == "active"


def test_normalize_distribution_flags_disabled():
    dist = {
        "Id": "E1234567890",
        "DomainName": "d123.cloudfront.net",
        "PriceClass": "PriceClass_100",
        "Enabled": False,
        "LastModifiedTime": _now(),
    }
    result = normalize_distribution(dist, tags={}, collected_at=_now())
    assert result.resource_type == "cloudfront_distribution"
    assert result.state == "disabled"
    assert "DISTRIBUTION_DISABLED" in result.warnings


def test_normalize_user_flags_stale_access_key():
    user = {"UserName": "old-service-account", "CreateDate": _now()}
    result = normalize_user(user, tags={}, key_age_days=120, collected_at=_now())
    assert result.resource_type == "iam_user"
    assert "STALE_ACCESS_KEY" in result.warnings
    assert result.state == "key-age-120d"


def test_normalize_user_no_active_key_is_not_flagged_stale():
    user = {"UserName": "console-only-user", "CreateDate": _now()}
    result = normalize_user(user, tags={"Environment": "dev"}, key_age_days=None, collected_at=_now())
    assert "STALE_ACCESS_KEY" not in result.warnings
    assert result.state == "no-active-key"
