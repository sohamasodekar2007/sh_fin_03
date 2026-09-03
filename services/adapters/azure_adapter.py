"""
AzureAdapter — talks to Azure Resource Manager (VM inventory) + Azure Cost
Management (PreTaxCost) once a service-principal client secret is stored
encrypted on the CloudAccount. No live Azure sandbox is wired for this
hackathon build, so `collect()` degrades to services.focus.sample_data's
synthetic Azure fleet through the same normalize_azure() path a live call
would use.
"""

from __future__ import annotations

import logging

from packages.schemas.schemas import CloudAccount
from packages.schemas.unified_resource import UnifiedResource
from services.adapters.base import CloudAdapter
from services.adapters.crypto import decrypt_credentials
from services.focus.normalizer import normalize_azure
from services.focus.sample_data import generate_azure_resources

logger = logging.getLogger(__name__)


class AzureAdapter(CloudAdapter):
    provider = "azure"

    async def validate_credentials(self, account: CloudAccount) -> bool:
        if not account.encrypted_credentials:
            return False
        try:
            client_secret = decrypt_credentials(account.encrypted_credentials)
            return bool(client_secret)
        except Exception as exc:  # noqa: BLE001
            logger.warning("azure_adapter: credential validation failed for %s: %s", account.id, exc)
            return False

    async def collect(self, account: CloudAccount) -> list[UnifiedResource]:
        # PLACEHOLDER for a live sandbox: swap this block for
        # azure-mgmt-compute + azure-mgmt-costmanagement client calls using
        # the decrypted service-principal secret, keeping normalize_azure()
        # as the final step so downstream agents see the same shape.
        logger.info("azure_adapter: no live Azure sandbox configured — using synthetic FOCUS-shaped fleet for %s.", account.id)
        raw_resources = generate_azure_resources(subscription_id=account.account_id)
        return [normalize_azure(r) for r in raw_resources]
