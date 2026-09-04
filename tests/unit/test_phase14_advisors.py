from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import MagicMock

from services.phase14.rds_advisor import RDSAdvisor
from services.phase14.s3_advisor import S3Advisor


def _factory(client_map: dict) -> MagicMock:
    factory = MagicMock()
    factory.client.side_effect = lambda service, region_name=None: client_map[service]
    return factory


def _cw_datapoints(values: list[float]) -> dict:
    return {"Datapoints": [{"Average": v} for v in values]}


def test_rds_advisor_flags_idle_instance():
    rds = MagicMock()
    paginator = MagicMock()
    paginator.paginate.return_value = [
        {
            "DBInstances": [
                {
                    "DBInstanceIdentifier": "prod-db-1",
                    "DBInstanceClass": "db.t3.micro",
                    "DBInstanceStatus": "available",
                    "TagList": [{"Key": "Environment", "Value": "prod"}],
                }
            ]
        }
    ]
    rds.get_paginator.return_value = paginator

    cloudwatch = MagicMock()
    cloudwatch.get_metric_statistics.side_effect = [
        _cw_datapoints([0.2, 0.1, 0.0]),  # DatabaseConnections
        _cw_datapoints([1.0, 2.0]),  # CPUUtilization
    ]

    advisor = RDSAdvisor(client_factory=_factory({"rds": rds, "cloudwatch": cloudwatch}), region="ap-south-1")
    recs = advisor.collect_recommendations()

    assert len(recs) == 1
    assert recs[0].resource_id == "prod-db-1"
    assert recs[0].requires_human_approval is True
    assert "7 days" in recs[0].rationale


def test_rds_advisor_skips_non_available_instances():
    rds = MagicMock()
    paginator = MagicMock()
    paginator.paginate.return_value = [
        {"DBInstances": [{"DBInstanceIdentifier": "creating-db", "DBInstanceStatus": "creating", "TagList": []}]}
    ]
    rds.get_paginator.return_value = paginator
    cloudwatch = MagicMock()

    advisor = RDSAdvisor(client_factory=_factory({"rds": rds, "cloudwatch": cloudwatch}), region="ap-south-1")
    assert advisor.collect_recommendations() == []


def test_rds_advisor_skips_active_instance():
    rds = MagicMock()
    paginator = MagicMock()
    paginator.paginate.return_value = [
        {"DBInstances": [{"DBInstanceIdentifier": "busy-db", "DBInstanceStatus": "available", "TagList": []}]}
    ]
    rds.get_paginator.return_value = paginator

    cloudwatch = MagicMock()
    cloudwatch.get_metric_statistics.side_effect = [
        _cw_datapoints([500.0, 480.0]),  # plenty of connections
        _cw_datapoints([60.0, 70.0]),  # high CPU
    ]

    advisor = RDSAdvisor(client_factory=_factory({"rds": rds, "cloudwatch": cloudwatch}), region="ap-south-1")
    assert advisor.collect_recommendations() == []


def test_rds_advisor_skips_when_no_metric_signal_at_all():
    rds = MagicMock()
    paginator = MagicMock()
    paginator.paginate.return_value = [
        {"DBInstances": [{"DBInstanceIdentifier": "no-data-db", "DBInstanceStatus": "available", "TagList": []}]}
    ]
    rds.get_paginator.return_value = paginator
    cloudwatch = MagicMock()
    cloudwatch.get_metric_statistics.return_value = {"Datapoints": []}

    advisor = RDSAdvisor(client_factory=_factory({"rds": rds, "cloudwatch": cloudwatch}), region="ap-south-1")
    assert advisor.collect_recommendations() == []


def test_s3_advisor_recommends_stable_bucket():
    s3 = MagicMock()
    s3.list_buckets.return_value = {"Buckets": [{"Name": "cold-bucket"}]}
    s3.get_bucket_lifecycle_configuration.side_effect = Exception("NoSuchLifecycleConfiguration")

    from botocore.exceptions import ClientError

    s3.get_bucket_lifecycle_configuration.side_effect = ClientError(
        {"Error": {"Code": "NoSuchLifecycleConfiguration", "Message": "none"}}, "GetBucketLifecycleConfiguration"
    )

    cloudwatch = MagicMock()
    now = datetime.now(timezone.utc)
    cloudwatch.get_metric_statistics.return_value = {
        "Datapoints": [
            {"Average": 1000.0, "Timestamp": now},
            {"Average": 1000.5, "Timestamp": now},
        ]
    }

    advisor = S3Advisor(client_factory=_factory({"s3": s3, "cloudwatch": cloudwatch}), region="ap-south-1")
    recs = advisor.collect_recommendations()

    assert len(recs) == 1
    assert recs[0].bucket == "cold-bucket"
    assert recs[0].suggested_storage_class == "STANDARD_IA"
    assert recs[0].requires_human_approval is True
    assert "heuristic" in recs[0].rationale


def test_s3_advisor_skips_bucket_with_real_size_movement():
    s3 = MagicMock()
    s3.list_buckets.return_value = {"Buckets": [{"Name": "active-bucket"}]}
    from botocore.exceptions import ClientError

    s3.get_bucket_lifecycle_configuration.side_effect = ClientError(
        {"Error": {"Code": "NoSuchLifecycleConfiguration", "Message": "none"}}, "GetBucketLifecycleConfiguration"
    )

    cloudwatch = MagicMock()
    now = datetime.now(timezone.utc)
    cloudwatch.get_metric_statistics.return_value = {
        "Datapoints": [
            {"Average": 1000.0, "Timestamp": now},
            {"Average": 5000.0, "Timestamp": now},
        ]
    }

    advisor = S3Advisor(client_factory=_factory({"s3": s3, "cloudwatch": cloudwatch}), region="ap-south-1")
    assert advisor.collect_recommendations() == []


def test_s3_advisor_skips_bucket_already_transitioned():
    s3 = MagicMock()
    s3.list_buckets.return_value = {"Buckets": [{"Name": "already-ia"}]}
    s3.get_bucket_lifecycle_configuration.return_value = {
        "Rules": [{"Transitions": [{"StorageClass": "STANDARD_IA"}]}]
    }
    cloudwatch = MagicMock()

    advisor = S3Advisor(client_factory=_factory({"s3": s3, "cloudwatch": cloudwatch}), region="ap-south-1")
    assert advisor.collect_recommendations() == []
