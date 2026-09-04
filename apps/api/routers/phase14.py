"""
Phase 14 router — three read-only, recommend/audit-only surfaces. Deleting
this file plus services/phase14/ plus the one include_router(phase14.router)
line in apps/api/main.py fully removes this feature; nothing else imports
from here.
"""

from __future__ import annotations

import asyncio

from fastapi import APIRouter
from pydantic import BaseModel

from apps.api.config import get_settings
from apps.api.dependencies import CurrentUser
from packages.aws.session import AWSClientFactory
from services.phase14.iam_security_findings import IAMSecurityFindingsCollector, IAMSecurityFindingsError
from services.phase14.rds_advisor import RDSAdvisor, RDSAdvisorError
from services.phase14.s3_advisor import S3Advisor, S3AdvisorError
from services.phase14.schemas import RDSRecommendation, S3Recommendation, SecurityFinding

router = APIRouter(prefix="/v1/phase14", tags=["phase14"])
_SECURITY_FINDINGS_TIMEOUT_SECONDS = 6.0


class RDSRecommendationsResponse(BaseModel):
    recommendations: list[RDSRecommendation] = []
    enabled: bool = True
    error: str | None = None


class S3RecommendationsResponse(BaseModel):
    recommendations: list[S3Recommendation] = []
    enabled: bool = True
    error: str | None = None


class SecurityFindingsResponse(BaseModel):
    findings: list[SecurityFinding] = []
    enabled: bool = True
    error: str | None = None


def _direct_credentials_factory(settings) -> AWSClientFactory | None:
    if not settings.aws_access_key_id or not settings.aws_secret_access_key:
        return None
    direct_settings = settings.model_copy(update={"aws_role_arn": "", "aws_read_role_arn": ""})
    return AWSClientFactory(direct_settings)


def _is_access_denied(error: Exception) -> bool:
    return "AccessDenied" in str(error) or "AccessDeniedException" in str(error)


@router.get("/rds-recommendations", response_model=RDSRecommendationsResponse)
async def get_rds_recommendations(current_user: CurrentUser) -> RDSRecommendationsResponse:
    settings = get_settings()
    if not settings.rds_advisor_enabled:
        return RDSRecommendationsResponse(recommendations=[], enabled=False)

    factory = AWSClientFactory(settings)
    try:
        recommendations = RDSAdvisor(client_factory=factory, region=settings.aws_region).collect_recommendations()
        return RDSRecommendationsResponse(recommendations=recommendations)
    except RDSAdvisorError as error:
        return RDSRecommendationsResponse(recommendations=[], error=str(error))


@router.get("/s3-recommendations", response_model=S3RecommendationsResponse)
async def get_s3_recommendations(current_user: CurrentUser) -> S3RecommendationsResponse:
    settings = get_settings()
    if not settings.s3_lifecycle_advisor_enabled:
        return S3RecommendationsResponse(recommendations=[], enabled=False)

    factory = AWSClientFactory(settings)
    try:
        recommendations = S3Advisor(client_factory=factory, region=settings.aws_region).collect_recommendations()
        return S3RecommendationsResponse(recommendations=recommendations)
    except S3AdvisorError as error:
        return S3RecommendationsResponse(recommendations=[], error=str(error))


@router.get("/security-findings", response_model=SecurityFindingsResponse)
async def get_security_findings(current_user: CurrentUser) -> SecurityFindingsResponse:
    settings = get_settings()
    if not settings.iam_security_findings_enabled:
        return SecurityFindingsResponse(findings=[], enabled=False)

    factory = AWSClientFactory(settings)
    try:
        findings = await asyncio.wait_for(
            asyncio.to_thread(IAMSecurityFindingsCollector(client_factory=factory).collect),
            timeout=_SECURITY_FINDINGS_TIMEOUT_SECONDS,
        )
        return SecurityFindingsResponse(findings=findings)
    except TimeoutError:
        return SecurityFindingsResponse(
            findings=[],
            error="IAM security review timed out; check AWS credentials/network and try again.",
        )
    except IAMSecurityFindingsError as error:
        direct_factory = _direct_credentials_factory(settings)
        if direct_factory is not None and _is_access_denied(error):
            try:
                findings = await asyncio.wait_for(
                    asyncio.to_thread(IAMSecurityFindingsCollector(client_factory=direct_factory).collect),
                    timeout=_SECURITY_FINDINGS_TIMEOUT_SECONDS,
                )
                return SecurityFindingsResponse(findings=findings)
            except TimeoutError:
                return SecurityFindingsResponse(
                    findings=[],
                    error="IAM security review timed out; check AWS credentials/network and try again.",
                )
            except IAMSecurityFindingsError as fallback_error:
                return SecurityFindingsResponse(findings=[], error=str(fallback_error))
        return SecurityFindingsResponse(findings=[], error=str(error))
