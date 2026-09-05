from __future__ import annotations

from fastapi import APIRouter
from pydantic import BaseModel

from demo.scenario import build_security_policy_addons_scenario
from security_policy_addons import (
    AccessKeySample,
    S3BucketExposure,
    SecurityGroupRule,
    SecurityPolicyFinding,
    StorageResource,
    check_open_security_groups,
    check_public_buckets,
    check_stale_access_keys,
    check_unencrypted_storage,
)

router = APIRouter(prefix="/security-policy-addons", tags=["security-policy-addons"])


class FindingsResponse(BaseModel):
    findings: list[SecurityPolicyFinding]


class EvaluateRequest(BaseModel):
    security_group_rules: list[SecurityGroupRule] = []
    storage_resources: list[StorageResource] = []
    s3_buckets: list[S3BucketExposure] = []
    access_keys: list[AccessKeySample] = []
    stale_key_max_age_days: int = 90


def _run_all(
    sg_rules: list[SecurityGroupRule],
    storage: list[StorageResource],
    buckets: list[S3BucketExposure],
    keys: list[AccessKeySample],
    *,
    max_age_days: int,
) -> list[SecurityPolicyFinding]:
    findings: list[SecurityPolicyFinding] = []
    findings += check_open_security_groups(sg_rules)
    findings += check_unencrypted_storage(storage)
    findings += check_public_buckets(buckets)
    findings += check_stale_access_keys(keys, max_age_days=max_age_days)
    return findings


@router.get("/demo-findings", response_model=FindingsResponse)
def demo_findings() -> FindingsResponse:
    scenario = build_security_policy_addons_scenario()
    findings = _run_all(
        [SecurityGroupRule(**r) for r in scenario["security_group_rules"]],
        [StorageResource(**r) for r in scenario["storage_resources"]],
        [S3BucketExposure(**r) for r in scenario["s3_buckets"]],
        [AccessKeySample(**r) for r in scenario["access_keys"]],
        max_age_days=90,
    )
    return FindingsResponse(findings=findings)


@router.post("/evaluate", response_model=FindingsResponse)
def evaluate(request: EvaluateRequest) -> FindingsResponse:
    findings = _run_all(
        request.security_group_rules,
        request.storage_resources,
        request.s3_buckets,
        request.access_keys,
        max_age_days=request.stale_key_max_age_days,
    )
    return FindingsResponse(findings=findings)
