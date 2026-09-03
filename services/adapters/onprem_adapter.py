"""
OnPremAdapter — a simulated VPS/colo fleet standing in for infrastructure
with no cloud billing API at all. Credentials (an SSH key, in a real
deployment) are still round-tripped through AES-256-GCM to prove the same
encrypted-onboarding path multi-cloud accounts use, even though nothing is
actually SSH'd into for this build.
"""

from __future__ import annotations

import logging

from packages.schemas.schemas import CloudAccount
from packages.schemas.unified_resource import UnifiedResource
from services.adapters.base import CloudAdapter
from services.focus.normalizer import normalize_onprem
from services.focus.sample_data import generate_onprem_resources

logger = logging.getLogger(__name__)


class OnPremAdapter(CloudAdapter):
    provider = "onprem"

    async def validate_credentials(self, account: CloudAccount) -> bool:
        return bool(account.encrypted_credentials)

    async def collect(self, account: CloudAccount) -> list[UnifiedResource]:
        logger.info("onprem_adapter: generating simulated VPS fleet for datacenter %s.", account.account_id)
        raw_resources = generate_onprem_resources(datacenter=account.account_id)
        return [normalize_onprem(r) for r in raw_resources]
