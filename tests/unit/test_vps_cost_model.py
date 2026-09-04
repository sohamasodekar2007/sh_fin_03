from __future__ import annotations

from decimal import Decimal, getcontext, localcontext

import pytest
from pydantic import ValidationError

from packages.schemas.schemas import ActionProposal
from services.analyzer.models import Finding
from services.focus.mappers.vps import map_vps_to_focus

TENANT = "demo-tenant"


@pytest.fixture(autouse=True)
def _wide_decimal_precision():
    """
    services/focus/mappers/vps.py computes at 50 digits of precision
    internally (see that module's comment on why 28 isn't enough for a
    repeating fraction like 1800/83). A stored Decimal keeps however many
    digits it was computed with regardless of the ambient context, but any
    *new* arithmetic on it here in the test — summing BilledCost across
    records, in particular — rounds its result back down to whatever the
    ambient context's precision is. Match the module under test for the
    duration of every test in this file, restore it after.
    """
    original_prec = getcontext().prec
    getcontext().prec = 50
    yield
    getcontext().prec = original_prec


def _resource(unit_id: str, vcpu: float, host_total_vcpu: float, resource_type: str = "vps_vm", **overrides) -> dict:
    base = {
        "resource_type": resource_type,
        "unit_id": unit_id,
        "resource_id": f"vps-01:{unit_id}",
        "name": unit_id,
        "vcpu_count": vcpu,
        "memory_mb": 2048,
        "host_total_vcpu": host_total_vcpu,
        "host_total_memory_mb": 8192,
        "host_total_disk_gb": 100,
        "tags": {},
    }
    base.update(overrides)
    return base


def _daily_usd(monthly: str, currency_rate: str = "83.0") -> Decimal:
    # Must match services/focus/mappers/vps.py's internal 50-digit
    # precision context exactly, or comparing against the mapper's own
    # (correctly) higher-precision result spuriously fails — see that
    # module's comment on why the default 28-digit context isn't enough.
    with localcontext() as ctx:
        ctx.prec = 50
        monthly_usd = Decimal(monthly) / Decimal(currency_rate)
        return monthly_usd * 12 / 365


# ---------------------------------------------------------------------------
# Reconciliation — the core requirement: exact equality, never approx
# ---------------------------------------------------------------------------


def test_allocation_reconciles_exactly_with_overhead_row_for_under_allocated_host():
    snapshot = {
        "host": "vps-01",
        "resources": [_resource("vm1", vcpu=1, host_total_vcpu=4)],
    }
    dataset = map_vps_to_focus(snapshot, TENANT, monthly_cost=Decimal("1800"), monthly_cost_currency="INR", usd_to_inr=83.0)

    expected_daily = _daily_usd("1800")
    total = sum((r.BilledCost for r in dataset.records), Decimal("0"))

    assert total == expected_daily  # exact, not approx
    assert dataset.row_count == 2
    resource_types = {r.ResourceType for r in dataset.records}
    assert "vps_host_overhead" in resource_types


def test_allocation_reconciles_exactly_when_fully_allocated_no_overhead_row():
    snapshot = {
        "host": "vps-01",
        "resources": [
            _resource("vm1", vcpu=1, host_total_vcpu=4),
            _resource("vm2", vcpu=3, host_total_vcpu=4),
        ],
    }
    dataset = map_vps_to_focus(snapshot, TENANT, monthly_cost=Decimal("1800"), monthly_cost_currency="INR", usd_to_inr=83.0)

    expected_daily = _daily_usd("1800")
    total = sum((r.BilledCost for r in dataset.records), Decimal("0"))

    assert total == expected_daily
    # Fully allocated (1+3 == 4 host total) — no separate overhead row, the
    # spurious Decimal round-trip noise this could otherwise produce is
    # folded into the last unit's row instead.
    assert dataset.row_count == 2
    resource_types = {r.ResourceType for r in dataset.records}
    assert "vps_host_overhead" not in resource_types


def test_allocation_reconciles_exactly_with_oversubscribed_vcpus():
    """6 allocated vCPU on a 4-vCPU host — shares must still sum to
    exactly 100% of daily_cost, with no negative or fabricated overhead."""
    snapshot = {
        "host": "vps-01",
        "resources": [
            _resource("vm1", vcpu=2, host_total_vcpu=4),
            _resource("vm2", vcpu=4, host_total_vcpu=4),
        ],
    }
    dataset = map_vps_to_focus(snapshot, TENANT, monthly_cost=Decimal("1800"), monthly_cost_currency="INR", usd_to_inr=83.0)

    expected_daily = _daily_usd("1800")
    total = sum((r.BilledCost for r in dataset.records), Decimal("0"))

    assert total == expected_daily
    assert all(r.BilledCost >= Decimal("0") for r in dataset.records)
    # vm2 has double vm1's vCPU share -> roughly double the cost.
    by_id = {r.ResourceId: r.BilledCost for r in dataset.records}
    vm1_cost = by_id["vps-01:vm1"]
    vm2_cost = by_id["vps-01:vm2"]
    assert vm2_cost > vm1_cost


@pytest.mark.parametrize("vcpu_counts", [[1], [1, 1], [2, 3], [1, 1, 1, 1], [5], [1, 2, 3, 4, 5]])
def test_allocation_always_reconciles_exactly_across_shapes(vcpu_counts):
    total_vcpu = sum(vcpu_counts)
    snapshot = {
        "host": "vps-01",
        "resources": [
            _resource(f"vm{i}", vcpu=v, host_total_vcpu=total_vcpu) for i, v in enumerate(vcpu_counts)
        ],
    }
    dataset = map_vps_to_focus(snapshot, TENANT, monthly_cost=Decimal("1800"), monthly_cost_currency="INR", usd_to_inr=83.0)

    expected_daily = _daily_usd("1800")
    total = sum((r.BilledCost for r in dataset.records), Decimal("0"))
    assert total == expected_daily


# ---------------------------------------------------------------------------
# Single-host box — one row carrying the full amount
# ---------------------------------------------------------------------------


def test_single_host_box_produces_exactly_one_row_with_full_amount():
    snapshot = {
        "host": "vps-02",
        "resources": [_resource("host", vcpu=2, host_total_vcpu=2, resource_type="vps_host")],
    }
    dataset = map_vps_to_focus(snapshot, TENANT, monthly_cost=Decimal("1800"), monthly_cost_currency="INR", usd_to_inr=83.0)

    assert dataset.row_count == 1
    assert dataset.records[0].BilledCost == _daily_usd("1800")
    assert dataset.records[0].ResourceType == "vps_host"


# ---------------------------------------------------------------------------
# Currency conversion + provenance
# ---------------------------------------------------------------------------


def test_inr_converts_to_usd_and_original_is_preserved_in_extensions():
    snapshot = {"host": "vps-01", "resources": [_resource("vm1", vcpu=2, host_total_vcpu=2)]}
    dataset = map_vps_to_focus(
        snapshot, TENANT, monthly_cost=Decimal("1800"), monthly_cost_currency="INR", usd_to_inr=83.0
    )

    record = dataset.records[0]
    assert record.BillingCurrency == "USD"

    expected_daily_usd = _daily_usd("1800")
    assert record.BilledCost == expected_daily_usd

    # x_OriginalBilledCost round-trips back to INR at the same rate.
    original = Decimal(record.extensions["x_OriginalBilledCost"])
    assert record.extensions["x_OriginalBillingCurrency"] == "INR"
    assert original == expected_daily_usd * Decimal("83.0")


def test_usd_native_currency_skips_conversion():
    snapshot = {"host": "vps-01", "resources": [_resource("vm1", vcpu=2, host_total_vcpu=2)]}
    dataset = map_vps_to_focus(
        snapshot, TENANT, monthly_cost=Decimal("21.60"), monthly_cost_currency="USD"
    )

    record = dataset.records[0]
    expected_daily_usd = _daily_usd("21.60", currency_rate="1")
    assert record.BilledCost == expected_daily_usd
    assert record.extensions["x_OriginalBillingCurrency"] == "USD"
    assert Decimal(record.extensions["x_OriginalBilledCost"]) == expected_daily_usd


def test_amortization_uses_365_not_30_times_12():
    """daily_cost = monthly * 12 / 365, not monthly / 30 — these differ
    (12*30 = 360 != 365), so asserting against the 30-day formula must fail."""
    snapshot = {"host": "vps-01", "resources": [_resource("vm1", vcpu=1, host_total_vcpu=1)]}
    dataset = map_vps_to_focus(snapshot, TENANT, monthly_cost=Decimal("3650"), monthly_cost_currency="USD")

    correct_daily = Decimal("3650") * 12 / 365
    wrong_daily_30 = Decimal("3650") / 30

    assert dataset.records[0].BilledCost == correct_daily
    assert dataset.records[0].BilledCost != wrong_daily_30


# ---------------------------------------------------------------------------
# FOCUS column conventions
# ---------------------------------------------------------------------------


def test_focus_columns_match_the_vps_convention():
    snapshot = {
        "host": "vps-01",
        "resources": [_resource("vm1", vcpu=2, host_total_vcpu=2, memory_mb=4096)],
    }
    dataset = map_vps_to_focus(
        snapshot, TENANT, monthly_cost=Decimal("1800"), monthly_cost_currency="INR",
        usd_to_inr=83.0, company_name="Team Alpha",
    )
    record = dataset.records[0]

    assert record.ProviderName == "Private"
    assert record.PublisherName == "Team Alpha"
    assert record.ServiceName == "Self-Managed Compute"
    assert record.ServiceCategory == "Compute"
    assert record.ChargeCategory == "Usage"
    assert record.ChargeFrequency == "Recurring"
    assert record.RegionId == "on-premises"
    assert record.ResourceId == "vps-01:vm1"
    assert record.SkuId == "2vcpu-4096mb"
    assert record.PricingQuantity == Decimal("2") * 24


def test_dataset_source_is_modelled():
    snapshot = {"host": "vps-01", "resources": [_resource("vm1", vcpu=1, host_total_vcpu=1)]}
    dataset = map_vps_to_focus(snapshot, TENANT, monthly_cost=Decimal("1800"), monthly_cost_currency="INR")
    assert dataset.source == "modelled"
    assert dataset.provider == "vps"
    assert dataset.granularity == "daily"


def test_empty_resources_returns_empty_dataset_with_warning():
    dataset = map_vps_to_focus({"host": "vps-01", "resources": []}, TENANT, monthly_cost=Decimal("1800"))
    assert dataset.row_count == 0
    assert dataset.records == []
    assert "no_vps_resources_to_allocate_cost_across" in dataset.warnings


# ---------------------------------------------------------------------------
# Savings semantics — VPS findings/proposals never claim a dollar saving
# ---------------------------------------------------------------------------


def test_finding_defaults_to_billable_savings_type():
    finding = Finding(rule_id="ec2.idle.v1", severity="medium", confidence=0.9, evidence={})
    assert finding.savings_type == "billable"


def test_finding_reclaimable_capacity_carries_vcpu_and_memory():
    finding = Finding(
        rule_id="vps.idle.v1",
        severity="medium",
        confidence=0.9,
        evidence={},
        savings_type="reclaimable_capacity",
        reclaimable_vcpu=2.0,
        reclaimable_memory_mb=4096.0,
    )
    d = finding.to_dict("vps-01:vm1")
    assert d["savings_type"] == "reclaimable_capacity"
    assert d["reclaimable_vcpu"] == 2.0
    assert d["reclaimable_memory_mb"] == 4096.0


def test_action_proposal_rejects_nonzero_savings_for_reclaimable_capacity():
    with pytest.raises(ValidationError):
        ActionProposal(
            resource_arn="vps://vps-01/vm1",
            action_type="stop_instance",
            template_id="vps.stop.v1",
            expected_monthly_savings=Decimal("14.20"),
            risk_level="low",
            confidence=0.9,
            provider="vps",
            savings_type="reclaimable_capacity",
        )


def test_action_proposal_allows_zero_savings_for_reclaimable_capacity():
    proposal = ActionProposal(
        resource_arn="vps://vps-01/vm1",
        action_type="stop_instance",
        template_id="vps.stop.v1",
        expected_monthly_savings=Decimal("0"),
        risk_level="low",
        confidence=0.9,
        provider="vps",
        savings_type="reclaimable_capacity",
        reclaimable_vcpu=2.0,
        reclaimable_memory_mb=4096.0,
    )
    assert proposal.expected_monthly_savings == Decimal("0")
    assert proposal.savings_type == "reclaimable_capacity"


def test_action_proposal_billable_savings_unaffected_by_the_new_validator():
    proposal = ActionProposal(
        resource_arn="arn:aws:ec2:ap-south-1:123:instance/i-1",
        action_type="stop_instance",
        template_id="ec2.stop.v1",
        expected_monthly_savings=Decimal("14.20"),
        risk_level="low",
        confidence=0.9,
    )
    assert proposal.savings_type == "billable"
    assert proposal.provider == "aws"
    assert proposal.expected_monthly_savings == Decimal("14.20")
