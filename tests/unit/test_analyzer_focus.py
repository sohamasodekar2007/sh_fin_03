from __future__ import annotations

from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest

from packages.schemas.focus import FocusDataset, FocusRecord
from services.analyzer.service import (
    _environment_from_tags,
    _normalized_resource_state,
    analyze_observation,
)
from services.focus.metrics import ResourceMetric

TENANT = "demo-tenant"
NOW = datetime(2026, 1, 15, 0, 0, 0, tzinfo=timezone.utc)


def _focus_record(**overrides) -> FocusRecord:
    base = dict(
        BillingAccountId="acct-1",
        BillingPeriodStart=NOW.replace(day=1),
        BillingPeriodEnd=NOW.replace(day=1) + timedelta(days=31),
        ChargePeriodStart=NOW,
        ChargePeriodEnd=NOW + timedelta(days=1),
        ChargeCategory="Usage",
        ChargeDescription="test charge",
        BilledCost=Decimal("10.00"),
        EffectiveCost=Decimal("10.00"),
        ProviderName="AWS",
        PublisherName="AWS",
        ServiceName="Amazon Elastic Compute Cloud - Compute",
        ServiceCategory="Compute",
        ResourceId="i-test1",
        Tags={},
    )
    base.update(overrides)
    record, warnings = FocusRecord.from_raw(base)
    assert warnings == [], f"unexpected conformance warnings in test fixture: {warnings}"
    return record


def _dataset(records: list[FocusRecord], provider: str = "aws", dataset_id: str = "ds-1") -> FocusDataset:
    dataset = FocusDataset(
        tenant_id=TENANT,
        provider=provider,
        account_id="acct-1",
        granularity="daily",
        source="synthesized",
        row_count=len(records),
        records=records,
    )
    dataset.dataset_id = dataset_id
    return dataset


def _idle_metric(resource_id: str, sample_count: int = 14) -> ResourceMetric:
    return ResourceMetric(
        resource_id=resource_id,
        tenant_id=TENANT,
        window_start=NOW - timedelta(days=14),
        window_end=NOW,
        cpu_p95=2.0,
        cpu_avg=1.5,
        mem_p95=90.0,
        network_p95_bytes=1_000.0,
        sample_count=sample_count,
    )


# ---------------------------------------------------------------------------
# Multi-provider dataset -> findings tagged with the right provider
# ---------------------------------------------------------------------------


def test_multiprovider_dataset_findings_tagged_with_correct_provider():
    aws_record = _focus_record(
        ResourceId="i-aws1", ProviderName="AWS", ServiceCategory="Compute",
    )
    azure_record = _focus_record(
        ResourceId="/subscriptions/s1/vm1", ProviderName="Microsoft", ServiceCategory="Compute",
    )
    dataset = _dataset([aws_record, azure_record], provider="mixed")

    metrics = [_idle_metric("i-aws1"), _idle_metric("/subscriptions/s1/vm1")]

    findings = analyze_observation(dataset, metrics)
    idle_findings = [f for f in findings if f["rule_id"] == "ec2.idle.v1"]

    assert len(idle_findings) == 2
    by_resource = {f["resource_id"]: f for f in idle_findings}
    assert by_resource["i-aws1"]["provider"] == "AWS"
    assert by_resource["/subscriptions/s1/vm1"]["provider"] == "Microsoft"


def test_findings_carry_service_name_category_and_focus_dataset_id():
    record = _focus_record(ResourceId="i-1", ServiceName="Amazon Elastic Compute Cloud - Compute")
    dataset = _dataset([record], dataset_id="ds-xyz")
    findings = analyze_observation(dataset, [_idle_metric("i-1")])

    idle = next(f for f in findings if f["rule_id"] == "ec2.idle.v1")
    assert idle["service_name"] == "Amazon Elastic Compute Cloud - Compute"
    assert idle["service_category"] == "Compute"
    assert idle["focus_dataset_id"] == "ds-xyz"
    assert idle["billed_cost_30d"] == pytest.approx(10.00)
    assert "focus_columns" in idle["evidence"]
    assert idle["evidence"]["focus_columns"]["ResourceId"] == "i-1"
    assert idle["evidence"]["focus_columns"]["ServiceCategory"] == "Compute"


# ---------------------------------------------------------------------------
# No metrics -> no idle finding, never a false positive
# ---------------------------------------------------------------------------


def test_resource_with_no_metrics_produces_no_idle_finding():
    record = _focus_record(ResourceId="i-no-metrics")
    dataset = _dataset([record])

    findings = analyze_observation(dataset, [])  # no resource_metrics at all

    assert not any(f["resource_id"] == "i-no-metrics" and f["rule_id"] == "ec2.idle.v1" for f in findings)


def test_resource_with_metrics_for_a_different_resource_id_produces_no_finding():
    """Confirms the join is really on ResourceId, not "first metric wins"."""
    record = _focus_record(ResourceId="i-target")
    dataset = _dataset([record])

    findings = analyze_observation(dataset, [_idle_metric("i-someone-else")])

    assert not any(f["resource_id"] == "i-target" for f in findings)


def test_resource_with_too_few_samples_produces_no_finding_not_a_false_positive():
    """A real but under-threshold sample_count must not be padded up to
    pass classify_idle's len(metrics) >= 7 gate."""
    record = _focus_record(ResourceId="i-thin-data")
    dataset = _dataset([record])
    thin_metric = _idle_metric("i-thin-data", sample_count=3)

    findings = analyze_observation(dataset, [thin_metric])

    assert not any(f["resource_id"] == "i-thin-data" for f in findings)


def test_non_compute_resource_never_gets_idle_or_overprovisioned_findings():
    record = _focus_record(ResourceId="disk-1", ServiceCategory="Storage", ServiceName="Amazon Elastic Block Store")
    dataset = _dataset([record])

    findings = analyze_observation(dataset, [_idle_metric("disk-1")])

    assert not any(f["rule_id"] in ("ec2.idle.v1", "ec2.overprovisioned.v1") for f in findings)


# ---------------------------------------------------------------------------
# Environment derived from Tags (case-insensitive: env, Environment, ENV)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "tags,expected",
    [
        ({"env": "prod"}, "prod"),
        ({"Environment": "production"}, "prod"),
        ({"ENV": "dev"}, "dev"),
        ({"Environment": "STAGING"}, "staging"),
        ({"Owner": "team-a"}, "unknown"),
        ({}, "unknown"),
    ],
)
def test_environment_from_tags_is_case_insensitive(tags, expected):
    assert _environment_from_tags(tags) == expected


def test_environment_derivation_feeds_into_nonprod_schedule_environment_field():
    """classify_nonprod_schedule receives whatever _environment_from_tags
    derives — verified indirectly since the FOCUS-native path's hour=12
    default means this rule never actually fires (see service.py's module
    docstring), so we check the derived value directly instead."""
    assert _environment_from_tags({"Environment": "Production"}) == "prod"
    assert _environment_from_tags({"env": "STAGE"}) == "staging"


# ---------------------------------------------------------------------------
# Unattached storage — FOCUS taxonomy + normalized state, not ID matching
# ---------------------------------------------------------------------------


def test_unattached_storage_detected_via_service_category_not_resource_id():
    record = _focus_record(
        ResourceId="disk-no-vol-prefix",  # deliberately not "vol-*"
        ServiceCategory="Storage",
        ServiceName="Amazon Elastic Block Store",
        ChargeCategory="Usage",
        extensions={"x_resource_state": "available"},
    )
    dataset = _dataset([record])

    findings = analyze_observation(dataset, [])
    unattached = [f for f in findings if f["rule_id"] == "ebs.unattached.v1"]

    assert len(unattached) == 1
    assert unattached[0]["resource_id"] == "disk-no-vol-prefix"


def test_unattached_storage_normalizes_azure_state_vocabulary():
    """Azure's disk_state is "unattached", not AWS's "available" —
    classify_unattached_ebs (unchanged) only checks for "available", so
    the adapter must translate provider vocabulary, not the rule."""
    record = _focus_record(
        ResourceId="/subscriptions/s1/disks/d1",
        ProviderName="Microsoft",
        ServiceCategory="Storage",
        ServiceName="Managed Disks",
        ChargeCategory="Usage",
        extensions={"x_resource_state": "unattached"},
    )
    dataset = _dataset([record], provider="azure")

    findings = analyze_observation(dataset, [])
    unattached = [f for f in findings if f["rule_id"] == "ebs.unattached.v1"]

    assert len(unattached) == 1
    assert unattached[0]["provider"] == "Microsoft"


def test_attached_storage_does_not_fire():
    record = _focus_record(
        ResourceId="disk-attached",
        ServiceCategory="Storage",
        ChargeCategory="Usage",
        extensions={"x_resource_state": "attached"},
    )
    dataset = _dataset([record])

    findings = analyze_observation(dataset, [])
    assert not any(f["rule_id"] == "ebs.unattached.v1" for f in findings)


def test_storage_resource_id_also_used_by_a_compute_row_is_excluded():
    storage_record = _focus_record(
        ResourceId="shared-id-1",
        ServiceCategory="Storage",
        ChargeCategory="Usage",
        extensions={"x_resource_state": "available"},
    )
    compute_record = _focus_record(
        ResourceId="shared-id-1",
        ServiceCategory="Compute",
        ChargeCategory="Usage",
    )
    dataset = _dataset([storage_record, compute_record])

    findings = analyze_observation(dataset, [])
    assert not any(f["rule_id"] == "ebs.unattached.v1" for f in findings)


def test_normalized_resource_state_helper():
    assert _normalized_resource_state(_focus_record(extensions={"x_resource_state": "Available"})) == "available"
    assert _normalized_resource_state(_focus_record(extensions={"x_resource_state": "Unattached"})) == "available"
    assert _normalized_resource_state(_focus_record(extensions={"x_resource_state": "in-use"})) == "in-use"
    assert _normalized_resource_state(_focus_record(extensions={})) == ""


# ---------------------------------------------------------------------------
# Spend anomaly — grouped by (ServiceName, ResourceId), daily-bucketed
# ---------------------------------------------------------------------------


def _flat_then_spike_records(resource_id: str, service_name: str = "Amazon EC2") -> list[FocusRecord]:
    records = []
    for day_offset in range(15):
        charge_start = NOW - timedelta(days=14 - day_offset)
        amount = Decimal("500.00") if day_offset < 14 else Decimal("500.00")  # placeholder, overwritten below
        records.append(
            _focus_record(
                ResourceId=resource_id,
                ServiceName=service_name,
                ChargePeriodStart=charge_start,
                ChargePeriodEnd=charge_start + timedelta(days=1),
                BilledCost=Decimal("10.00") if day_offset < 14 else Decimal("100.00"),
                EffectiveCost=Decimal("10.00") if day_offset < 14 else Decimal("100.00"),
            )
        )
    return records


def test_spend_anomaly_fires_per_service_resource_group():
    records = _flat_then_spike_records("i-anomaly")
    dataset = _dataset(records)

    findings = analyze_observation(dataset, [])
    anomalies = [f for f in findings if f["rule_id"] == "cost.anomaly.v1" and f["resource_id"] == "i-anomaly"]

    assert len(anomalies) == 1
    assert anomalies[0]["service_name"] == "Amazon EC2"


def test_spend_anomaly_buckets_multiple_same_day_rows_before_comparing():
    """Hourly-granularity records for the same day must be summed into one
    daily total, not treated as separate 'days' in the series."""
    records = []
    for day_offset in range(15):
        charge_day = NOW - timedelta(days=14 - day_offset)
        daily_amount = Decimal("10.00") if day_offset < 14 else Decimal("100.00")
        # Split the day's total across 4 hourly rows.
        for hour in range(4):
            charge_start = charge_day + timedelta(hours=hour * 6)
            records.append(
                _focus_record(
                    ResourceId="i-hourly",
                    ChargePeriodStart=charge_start,
                    ChargePeriodEnd=charge_start + timedelta(hours=6),
                    BilledCost=daily_amount / 4,
                    EffectiveCost=daily_amount / 4,
                )
            )
    dataset = _dataset(records)

    findings = analyze_observation(dataset, [])
    anomalies = [f for f in findings if f["rule_id"] == "cost.anomaly.v1" and f["resource_id"] == "i-hourly"]

    assert len(anomalies) == 1
    assert anomalies[0]["evidence"]["current_day_usd"] == pytest.approx(100.00, rel=1e-2)


def test_account_level_spend_anomaly_still_fires():
    resource_a = _flat_then_spike_records("i-a")
    resource_b = _flat_then_spike_records("i-b")
    dataset = _dataset(resource_a + resource_b)

    findings = analyze_observation(dataset, [])
    account_level = [f for f in findings if f["resource_id"] == "account-billing-history"]

    assert len(account_level) == 1
    assert account_level[0]["rule_id"] == "cost.anomaly.v1"


# ---------------------------------------------------------------------------
# Empty dataset degrades gracefully
# ---------------------------------------------------------------------------


def test_empty_dataset_produces_no_findings_without_error():
    dataset = _dataset([])
    assert analyze_observation(dataset, []) == []
