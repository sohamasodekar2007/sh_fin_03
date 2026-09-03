"""
CloudAdapter — the interface every provider (AWS, GCP, Azure, on-prem) must
satisfy so the rest of the pipeline (FOCUS normalizer, Analyzer, Decision,
Supervisor, Executor) never branches on `provider`.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

from packages.schemas.schemas import CloudAccount
from packages.schemas.unified_resource import UnifiedResource


class CloudAdapter(ABC):
    provider: str

    @abstractmethod
    async def validate_credentials(self, account: CloudAccount) -> bool:
        """Cheap, side-effect-free check that the stored credentials/role
        can actually authenticate against the provider."""
        raise NotImplementedError

    @abstractmethod
    async def collect(self, account: CloudAccount) -> list[UnifiedResource]:
        """Pull raw inventory + cost + utilization telemetry and return it
        already normalized to the FOCUS 1.0 UnifiedResource schema."""
        raise NotImplementedError

    @staticmethod
    def _percentile(values: list[float], pct: float) -> float:
        if not values:
            return 0.0
        ordered = sorted(values)
        k = (len(ordered) - 1) * (pct / 100)
        lower = int(k)
        upper = min(lower + 1, len(ordered) - 1)
        if lower == upper:
            return ordered[lower]
        return ordered[lower] + (ordered[upper] - ordered[lower]) * (k - lower)


def get_adapter(provider: str) -> CloudAdapter:
    if provider == "aws":
        from services.adapters.aws_adapter import AwsAdapter
        return AwsAdapter()
    if provider == "gcp":
        from services.adapters.gcp_adapter import GcpAdapter
        return GcpAdapter()
    if provider == "azure":
        from services.adapters.azure_adapter import AzureAdapter
        return AzureAdapter()
    if provider == "onprem":
        from services.adapters.onprem_adapter import OnPremAdapter
        return OnPremAdapter()
    raise ValueError(f"Unknown cloud provider: {provider}")
