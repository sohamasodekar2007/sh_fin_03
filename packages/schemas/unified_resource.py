"""
FOCUS 1.0-inspired canonical schema — the normalization target for every
cloud adapter (AWS, GCP, Azure, on-prem). Field names follow the FinOps
Open Cost & Usage Specification (FOCUS) 1.0 column naming where a direct
analogue exists (BilledCost, EffectiveCost, ServiceCategory, ChargePeriod*),
so a real FOCUS 1.0 / AWS CUR export can be loaded with a thin column-rename
instead of a bespoke parser per provider.

`services.focus.normalizer` is the only place that constructs these from
raw per-provider telemetry — nothing downstream (analyzer, decision,
policy, executor) should know AWS/GCP/Azure/on-prem shapes exist.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Literal

from pydantic import BaseModel, Field

Provider = Literal["aws", "gcp", "azure", "onprem"]

ServiceCategory = Literal[
    "Compute",
    "Storage",
    "Database",
    "Networking",
    "Analytics",
    "Other",
]

ChargeCategory = Literal["Usage", "Purchase", "Tax", "Credit", "Adjustment"]


class UnifiedResource(BaseModel):
    schema_version: Literal["focus-1.0"] = "focus-1.0"

    # --- Identity -----------------------------------------------------
    id: str
    provider: Provider
    account_id: str
    resource_name: str | None = None
    resource_type: str
    service_category: ServiceCategory
    service_name: str

    # --- Location -------------------------------------------------------
    region: str
    availability_zone: str | None = None

    # --- FOCUS cost columns ----------------------------------------------
    billed_cost: float = Field(ge=0, description="FOCUS BilledCost — invoiced amount")
    effective_cost: float = Field(ge=0, description="FOCUS EffectiveCost — post-discount/credit amortized cost")
    list_cost: float = Field(ge=0, description="FOCUS ListCost — undiscounted list-price cost")
    pricing_currency: str = "USD"
    charge_category: ChargeCategory = "Usage"
    billing_period_start: datetime
    billing_period_end: datetime

    # --- Runtime telemetry (not in FOCUS core, appended for the Analyzer) ---
    state: str = "unknown"
    environment: str = "unknown"
    metrics_cpu_utilization_p95: float | None = None
    metrics_memory_utilization_p95: float | None = None
    metrics_network_bytes_p95: float | None = None

    # Not part of FOCUS 1.0 proper — an internal appendix so the Analyzer
    # Agent's rule functions (which classify over a rolling window, not a
    # single percentile) have real per-day series to work with. Populated
    # by the adapter (a true 14-day CloudWatch series for live AWS, a
    # deterministically-seeded series for every mock/simulated path) and
    # never persisted to the `resources` Mongo collection.
    metrics_cpu_samples: list[float] = Field(default_factory=list)
    metrics_network_bytes_samples: list[float] = Field(default_factory=list)

    # --- Governance -------------------------------------------------------
    tags: dict[str, str] = Field(default_factory=dict)
    owner: str | None = None

    collected_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    def to_dashboard_resource(self) -> dict:
        """Adapter to the lightweight `Resource` shape the existing REST
        routers / dashboard components already expect, so the frontend
        contract doesn't need to change just because ingestion went
        multi-cloud."""
        from packages.schemas.schemas import Resource

        cpu = self.metrics_cpu_utilization_p95 or 0.0
        if cpu < 5:
            status = "Idle"
        elif cpu > 85:
            status = "At-risk"
        elif (self.metrics_memory_utilization_p95 or 100) > 60 and cpu < 25:
            status = "Over-provisioned"
        else:
            status = "Healthy"

        env = self.environment.lower()
        env_literal = env if env in ("dev", "staging", "prod") else "dev"

        return Resource(
            id=self.id,
            type=self.resource_type,
            region=self.region,
            cpu_p95=cpu,
            status=status,
            monthly_cost_usd=self.effective_cost,
            tags={**self.tags, "provider": self.provider},
            owner=self.owner,
            environment=env_literal,  # type: ignore[arg-type]
        ).model_dump()
