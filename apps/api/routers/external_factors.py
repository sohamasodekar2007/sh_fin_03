from __future__ import annotations

from typing import Any

from fastapi import APIRouter

from apps.api.dependencies import CurrentUser
from services.external_factors.aws_core_services import aws_core_services_payload

router = APIRouter(prefix="/v1/external-factors", tags=["external-factors"])


@router.get("/aws-core-services")
async def get_aws_core_services(current_user: CurrentUser) -> dict[str, Any]:
    return aws_core_services_payload()
