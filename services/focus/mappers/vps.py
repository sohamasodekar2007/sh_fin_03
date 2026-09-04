"""
Maps a company-owned VPS into FOCUS 1.0 rows.

Structurally different from AWS/Azure (services/focus/mappers/aws.py,
azure.py): there is no billing API to observe or export, ever — a VPS's
cost can only be MODELLED from a fixed monthly figure. FocusDataset.source
is "modelled" here, a fourth value alongside "live_export", "synthesized"
and "sample", so the UI can tell a modelled cost apart from an observed one.

AMORTIZATION: daily_cost = monthly_usd * 12 / 365. Not monthly/30 — that
drifts against the real annual total (30*12=360 != 365).

ALLOCATION: by ALLOCATED vCPU share, never usage. Usage-weighted allocation
is rejected on purpose — it would make an idle VM cheaper, which directly
defeats the idle-detection rule the rest of this system relies on.

RECONCILIATION: computed as a residual, not two independent formulas — each
unit's share is daily_cost * (unit_vcpu / denominator), and the
"vps_host_overhead" row is exactly daily_cost minus the sum of every unit's
share. That guarantees the total always equals daily_cost exactly (Decimal,
never float), regardless of Decimal-division rounding inside individual
shares, and handles vCPU oversubscription (allocated vCPU > physical cores)
by widening the denominator to the larger of the two so shares never sum
past 100%.

SAVINGS SEMANTICS: stopping a VM on a fixed-price server saves nothing —
the monthly cost is owed either way. VPS findings/proposals must use
savings_type="reclaimable_capacity" with expected_monthly_savings == 0 (see
packages/schemas/schemas.py and services/analyzer/models.py) — this mapper
only produces the cost side of that story, not findings.
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from decimal import Decimal, localcontext
from typing import Any

from packages.schemas.focus import FocusDataset, FocusRecord

logger = logging.getLogger(__name__)

DEFAULT_USD_TO_INR = 83.0
DEFAULT_COMPANY_NAME = "CloudCare"

_DAYS_PER_YEAR = Decimal(365)
_MONTHS_PER_YEAR = Decimal(12)
_HOURS_PER_DAY = Decimal(24)


def _billing_period_bounds(charge_start: datetime) -> tuple[datetime, datetime]:
    month_start = charge_start.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    if month_start.month == 12:
        next_month_start = month_start.replace(year=month_start.year + 1, month=1)
    else:
        next_month_start = month_start.replace(month=month_start.month + 1)
    return month_start, next_month_start


def _to_decimal(value: Any) -> Decimal:
    if isinstance(value, Decimal):
        return value
    return Decimal(str(value))


def map_vps_to_focus(
    snapshot: dict[str, Any],
    tenant_id: str,
    monthly_cost: Decimal | str | float,
    monthly_cost_currency: str = "INR",
    usd_to_inr: float = DEFAULT_USD_TO_INR,
    company_name: str = DEFAULT_COMPANY_NAME,
) -> FocusDataset:
    """
    snapshot: {"host": str, "resources": list[dict]} where each resource
    dict is a VPSResourceRecord.model_dump() (resource_type, unit_id,
    resource_id, vcpu_count, host_total_vcpu, tags, ...).
    """
    host = snapshot.get("host", "") or "vps-host"
    resources: list[dict[str, Any]] = snapshot.get("resources") or []
    account_id = snapshot.get("account_id") or host

    monthly_cost_decimal = _to_decimal(monthly_cost)
    currency = (monthly_cost_currency or "INR").upper()

    if not resources:
        return FocusDataset(
            tenant_id=tenant_id,
            provider="vps",
            account_id=account_id,
            granularity="daily",
            source="modelled",
            row_count=0,
            records=[],
            warnings=["no_vps_resources_to_allocate_cost_across"],
        )

    now = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
    charge_start = now
    charge_end = now + timedelta(days=1)
    billing_start, billing_end = _billing_period_bounds(charge_start)

    total_host_vcpu = _to_decimal(resources[0].get("host_total_vcpu", 0)) if resources else Decimal("0")
    total_unit_vcpu = sum((_to_decimal(r.get("vcpu_count", 0)) for r in resources), Decimal("0"))
    # Widen the denominator to whichever is larger so allocated shares never
    # sum past 100% of daily_cost when vCPUs are oversubscribed across units.
    denominator = max(total_host_vcpu, total_unit_vcpu)

    records: list[FocusRecord] = []
    warnings: list[str] = []
    allocated_total = Decimal("0")

    # The default 28-digit Decimal context is enough for any single value
    # here, but a chained multiply-then-divide-by-the-same-number (as
    # happens whenever a unit holds 100% of the host's vCPUs) can lose its
    # last digit at 28 digits of precision, producing a spurious non-zero
    # residual below. 50 digits gives enough headroom that it round-trips
    # exactly for every case this domain's numbers (small monthly costs,
    # single/double-digit vCPU counts) can produce.
    # Whether unallocated host capacity genuinely exists — decided from the
    # vCPU counts themselves, never from whether a residual happens to come
    # out to exactly zero (repeating decimals like 1800/83 mean a
    # multiply-then-divide-by-the-same-number round trip can miss its last
    # digit at any finite precision, producing arithmetic noise on the
    # order of 1E-28 even when a single unit legitimately holds 100% of the
    # host — that noise must never masquerade as a fake overhead line item).
    has_unallocated_capacity = denominator > total_unit_vcpu

    with localcontext() as ctx:
        ctx.prec = 50

        # The currency conversion must happen inside this widened-precision
        # context too, not before it — dividing at the default 28-digit
        # context and only widening precision for the later multiply would
        # still truncate monthly_usd's last digits before they ever reach
        # the allocation math below, defeating the point of widening at all.
        if currency == "USD":
            monthly_usd = monthly_cost_decimal
            conversion_rate_to_original = Decimal("1")
        else:
            rate = _to_decimal(usd_to_inr) if usd_to_inr else Decimal(str(DEFAULT_USD_TO_INR))
            monthly_usd = monthly_cost_decimal / rate
            # original = usd * conversion_rate_to_original — reconstructs
            # the exact original-currency figure for x_OriginalBilledCost
            # below, rather than re-deriving it (which could drift from a
            # second independent multiply/divide).
            conversion_rate_to_original = rate

        daily_cost_usd = monthly_usd * _MONTHS_PER_YEAR / _DAYS_PER_YEAR

        for index, resource in enumerate(resources):
            unit_vcpu = _to_decimal(resource.get("vcpu_count", 0))
            share = (daily_cost_usd * unit_vcpu / denominator) if denominator > 0 else Decimal("0")
            allocated_total += share

            memory_mb = resource.get("memory_mb", 0)
            resource_id = resource.get("resource_id") or f"{host}:{resource.get('unit_id', index)}"
            unit_id = resource.get("unit_id", str(index))
            pricing_quantity = unit_vcpu * _HOURS_PER_DAY
            original_share = share * conversion_rate_to_original

            raw = {
                "BillingAccountId": account_id,
                "BillingPeriodStart": billing_start,
                "BillingPeriodEnd": billing_end,
                "ChargePeriodStart": charge_start,
                "ChargePeriodEnd": charge_end,
                "ChargeCategory": "Usage",
                "ChargeDescription": (
                    f"Amortized share of {host}'s monthly VPS cost for {unit_id} "
                    f"({unit_vcpu} vCPU of {denominator} allocated)"
                ),
                "ChargeFrequency": "Recurring",
                "BilledCost": share,
                "EffectiveCost": share,
                "BillingCurrency": "USD",
                "ProviderName": "Private",
                "PublisherName": company_name,
                "RegionId": "on-premises",
                "ResourceId": resource_id,
                "ResourceName": resource.get("name", unit_id),
                "ResourceType": resource.get("resource_type", "vps_vm"),
                "ServiceCategory": "Compute",
                "ServiceName": "Self-Managed Compute",
                "SkuId": f"{unit_vcpu}vcpu-{memory_mb}mb",
                "PricingQuantity": pricing_quantity,
                "PricingUnit": "vCPU-Hours",
                "PricingCategory": "Standard",
                "Tags": resource.get("tags") or {},
                "extensions": {
                    "x_allocation_method": "vcpu_share_of_fixed_monthly_cost",
                    "x_OriginalBilledCost": str(original_share),
                    "x_OriginalBillingCurrency": currency,
                },
            }
            record, row_warnings = FocusRecord.from_raw(raw)
            warnings.extend(f"{w}:row_{index}" for w in row_warnings)
            records.append(record)

        # The residual — never re-derived independently, so the total
        # always reconciles to daily_cost_usd exactly regardless of
        # Decimal rounding inside individual shares above.
        overhead_share = daily_cost_usd - allocated_total

        if has_unallocated_capacity and overhead_share != Decimal("0"):
            overhead_original = overhead_share * conversion_rate_to_original
            unallocated_vcpu = denominator - total_unit_vcpu
            raw = {
                "BillingAccountId": account_id,
                "BillingPeriodStart": billing_start,
                "BillingPeriodEnd": billing_end,
                "ChargePeriodStart": charge_start,
                "ChargePeriodEnd": charge_end,
                "ChargeCategory": "Usage",
                "ChargeDescription": (
                    f"Unallocated capacity on {host} ({unallocated_vcpu} vCPU not assigned to any unit)"
                ),
                "ChargeFrequency": "Recurring",
                "BilledCost": overhead_share,
                "EffectiveCost": overhead_share,
                "BillingCurrency": "USD",
                "ProviderName": "Private",
                "PublisherName": company_name,
                "RegionId": "on-premises",
                "ResourceId": f"{host}:vps_host_overhead",
                "ResourceName": "Unallocated host capacity",
                "ResourceType": "vps_host_overhead",
                "ServiceCategory": "Compute",
                "ServiceName": "Self-Managed Compute",
                "SkuId": f"{unallocated_vcpu}vcpu-overhead",
                "PricingQuantity": unallocated_vcpu * _HOURS_PER_DAY if unallocated_vcpu > 0 else Decimal("0"),
                "PricingUnit": "vCPU-Hours",
                "Tags": {},
                "extensions": {
                    "x_allocation_method": "vcpu_share_of_fixed_monthly_cost",
                    "x_OriginalBilledCost": str(overhead_original),
                    "x_OriginalBillingCurrency": currency,
                },
            }
            record, row_warnings = FocusRecord.from_raw(raw)
            warnings.extend(f"{w}:row_overhead" for w in row_warnings)
            records.append(record)
        elif overhead_share != Decimal("0") and records:
            # No real unallocated capacity (every vCPU is claimed by some
            # unit) — this residual is pure Decimal round-trip noise from a
            # non-terminating fraction (e.g. 1800/83), not a cost that
            # belongs to anyone. Fold it into the last unit's row instead
            # of manufacturing a fake "overhead" line item for capacity
            # that doesn't actually exist.
            last = records[-1]
            last.BilledCost = last.BilledCost + overhead_share
            last.EffectiveCost = last.EffectiveCost + overhead_share
            last.extensions["x_OriginalBilledCost"] = str(
                Decimal(last.extensions["x_OriginalBilledCost"]) + overhead_share * conversion_rate_to_original
            )

    logger.info(
        "focus.vps_mapper: modelled %d FOCUS rows for tenant=%s host=%s "
        "(daily_cost_usd=%s, %d resources, %d warnings)",
        len(records), tenant_id, host, daily_cost_usd, len(resources), len(warnings),
    )

    return FocusDataset(
        tenant_id=tenant_id,
        provider="vps",
        account_id=account_id,
        granularity="daily",
        source="modelled",
        row_count=len(records),
        records=records,
        warnings=warnings,
    )


def map_account_to_focus(tenant_id: str, account_id: str = "") -> FocusDataset:
    """
    Back-compat shim for callers written against the Phase 2 placeholder
    signature (services/focus/mappers/{gcp,azure}.py's account-based
    style). Returns an empty, honestly-labeled dataset — the real entry
    point is map_vps_to_focus(), which needs an actual snapshot and cost
    config that this signature has no way to provide.
    """
    logger.warning(
        "focus.vps_mapper: map_account_to_focus() called with no snapshot/cost config — "
        "use map_vps_to_focus(snapshot, tenant_id, monthly_cost, ...) instead"
    )
    return FocusDataset(
        tenant_id=tenant_id,
        provider="vps",
        account_id=account_id,
        granularity="daily",
        source="modelled",
        row_count=0,
        records=[],
        warnings=["map_account_to_focus_is_a_stub_use_map_vps_to_focus"],
    )
