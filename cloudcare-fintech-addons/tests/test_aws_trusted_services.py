from __future__ import annotations

import pytest

from aws_trusted_services import ServiceUsageSample, build_scorecard, check_approved_services
from aws_trusted_services.scorecard import score_pillar


def test_check_approved_services_flags_unapproved_only():
    usage = [
        ServiceUsageSample(service="ec2", resource_count=10, monthly_cost=500.0),
        ServiceUsageSample(service="redshift", resource_count=1, monthly_cost=2000.0),
    ]
    report = check_approved_services(usage, approved_services=["ec2", "rds", "s3"])
    assert len(report.unapproved) == 1
    assert report.unapproved[0].service == "redshift"


def test_check_approved_services_is_case_insensitive():
    usage = [ServiceUsageSample(service="EC2", resource_count=1, monthly_cost=10.0)]
    report = check_approved_services(usage, approved_services=["ec2"])
    assert report.unapproved == []


def test_check_approved_services_computes_unapproved_pct():
    usage = [
        ServiceUsageSample(service="ec2", resource_count=1, monthly_cost=100.0),
        ServiceUsageSample(service="redshift", resource_count=1, monthly_cost=300.0),
    ]
    report = check_approved_services(usage, approved_services=["ec2"])
    assert report.total_cost == 400.0
    assert report.unapproved_cost == 300.0
    assert report.unapproved_pct == 75.0


def test_check_approved_services_empty_usage_no_division_by_zero():
    report = check_approved_services([], approved_services=["ec2"])
    assert report.unapproved_pct == 0.0
    assert report.total_cost == 0.0


def test_score_pillar_perfect_when_no_findings():
    score = score_pillar("security", 0)
    assert score.score == 100.0


def test_score_pillar_floors_at_zero():
    score = score_pillar("security", 50, critical_count=10)
    assert score.score == 0.0


def test_score_pillar_rejects_critical_exceeding_total():
    with pytest.raises(ValueError):
        score_pillar("security", 2, critical_count=5)


def test_build_scorecard_averages_pillars_and_assigns_grade():
    scorecard = build_scorecard(
        {
            "cost_optimization": (0, 0),
            "security": (2, 1),
            "fault_tolerance": (0, 0),
            "service_limits": (0, 0),
        }
    )
    assert len(scorecard.pillars) == 4
    security = next(p for p in scorecard.pillars if p.pillar == "security")
    assert security.score == pytest.approx(100 - 2 * 8 - 1 * 12)
    assert scorecard.overall_score == pytest.approx((100 + security.score + 100 + 100) / 4)
    assert scorecard.overall_grade in {"A", "B", "C", "D", "F"}


def test_build_scorecard_empty_input_is_perfect_score():
    scorecard = build_scorecard({})
    assert scorecard.overall_score == 100.0
    assert scorecard.overall_grade == "A"
