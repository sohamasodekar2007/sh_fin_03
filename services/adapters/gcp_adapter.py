"""
GcpAdapter — talks to Google Cloud (Compute Engine inventory + Cloud
Billing export) once a service-account JSON is stored encrypted on the
CloudAccount. No live GCP sandbox is wired for this hackathon build, so
`collect()` degrades straight to services.focus.sample_data's synthetic GCP
fleet — but the decrypt call, adapter interface, and normalization path are
all real and exercised the same way a live call would be.
"""

from __future__ import annotations

import json
import logging

from packages.schemas.schemas import CloudAccount
from packages.schemas.unified_resource import UnifiedResource
from services.adapters.base import CloudAdapter
from services.adapters.crypto import decrypt_credentials
from services.focus.normalizer import normalize_gcp
from services.focus.sample_data import generate_gcp_resources

logger = logging.getLogger(__name__)


class GcpAdapter(CloudAdapter):
    provider = "gcp"

    async def validate_credentials(self, account: CloudAccount) -> bool:
        if not account.encrypted_credentials:
            return False
        try:
            service_account = json.loads(decrypt_credentials(account.encrypted_credentials))
            return bool(service_account.get("client_email") and service_account.get("private_key"))
        except Exception as exc:  # noqa: BLE001
            logger.warning("gcp_adapter: credential validation failed for %s: %s", account.id, exc)
            return False

    async def collect(self, account: CloudAccount) -> list[UnifiedResource]:
        # PLACEHOLDER for a live sandbox: once a real service-account JSON is
        # onboarded, replace this block with google-cloud-compute +
        # google-cloud-billing client calls, keeping the same normalize_gcp()
        # call at the end so nothing downstream changes.
        logger.info("gcp_adapter: no live GCP sandbox configured — using synthetic FOCUS-shaped fleet for %s.", account.id)
        raw_resources = generate_gcp_resources(project_id=account.account_id)
        return [normalize_gcp(r) for r in raw_resources]
