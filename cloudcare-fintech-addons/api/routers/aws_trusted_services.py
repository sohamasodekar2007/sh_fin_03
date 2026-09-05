from __future__ import annotations

from fastapi import APIRouter
from pydantic import BaseModel

from aws_trusted_services import ServiceUsageSample, TrustedServicesReport, TrustScorecard, build_scorecard, check_approved_services
from demo.scenario import build_security_policy_addons_scenario, build_trusted_services_scenario
from security_policy_addons import (
    AccessKeySample,
    S3BucketExposure,
    SecurityGroupRule,
    StorageResource,
    check_open_security_groups,
    check_public_buckets,
    check_stale_access_keys,
    check_unencrypted_storage,
)

router = APIRouter(prefix="/aws-trusted-services", tags=["aws-trusted-services"])


class AllowlistRequest(BaseModel):
    usage: list[ServiceUsageSample]
    approved_services: list[str]


@router.get("/demo-allowlist-report", response_model=TrustedServicesReport)
def demo_allowlist_report() -> TrustedServicesReport:
    usage_raw, approved = build_trusted_services_scenario()
    return check_approved_services([ServiceUsageSample(**u) for u in usage_raw], approved_services=approved)


@router.post("/allowlist-report", response_model=TrustedServicesReport)
def allowlist_report(request: AllowlistRequest) -> TrustedServicesReport:
    return check_approved_services(request.usage, approved_services=request.approved_services)


@router.get("/demo-scorecard", response_model=TrustScorecard)
def demo_scorecard() -> TrustScorecard:
    """Security pillar is fed by security_policy_addons' own findings
    (same demo scenario that /security-policy-addons/demo-findings uses),
    so the scorecard's security score and that panel's finding list can
    never silently disagree. The other three pillars have no add-on
    package behind them yet, so they report a clean 0-finding baseline —
    an honest "nothing checked here yet," not a fabricated good score."""
    scenario = build_security_policy_addons_scenario()
    findings = (
        check_open_security_groups([SecurityGroupRule(**r) for r in scenario["security_group_rules"]])
        + check_unencrypted_storage([StorageResource(**r) for r in scenario["storage_resources"]])
        + check_public_buckets([S3BucketExposure(**r) for r in scenario["s3_buckets"]])
        + check_stale_access_keys([AccessKeySample(**r) for r in scenario["access_keys"]])
    )
    critical_count = sum(1 for f in findings if f.severity == "critical")
    return build_scorecard(
        {
            "security": (len(findings), critical_count),
            "cost_optimization": (0, 0),
            "fault_tolerance": (0, 0),
            "service_limits": (0, 0),
        }
    )
