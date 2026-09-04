from __future__ import annotations

import pytest
from pydantic import ValidationError

from unit_economics.engine import compute_margin, compute_unit_cost, flag_negative_margin_scopes
from unit_economics.schemas import BusinessMetricSample
from unit_economics.seed_data import generate_merchant_samples


def test_compute_unit_cost_basic():
    sample = BusinessMetricSample(
        scope="merchant-a", period="2026-09", metric_name="transactions", metric_value=1000, cost=180.0
    )
    result = compute_unit_cost(sample)
    assert result.cost_per_unit == pytest.approx(0.18)


def test_metric_value_must_be_positive():
    with pytest.raises(ValidationError):
        BusinessMetricSample(scope="x", period="p", metric_name="transactions", metric_value=0, cost=10.0)


def test_compute_margin_returns_none_without_revenue():
    sample = BusinessMetricSample(
        scope="merchant-a", period="2026-09", metric_name="transactions", metric_value=1000, cost=180.0, revenue=None
    )
    assert compute_margin(sample) is None


def test_compute_margin_flags_negative_margin():
    sample = BusinessMetricSample(
        scope="merchant-x",
        period="2026-09",
        metric_name="transactions",
        metric_value=1000,
        cost=900.0,
        revenue=600.0,
    )
    result = compute_margin(sample)
    assert result is not None
    assert result.gross_margin_pct == pytest.approx(-50.0)  # (600-900)/600
    assert result.is_negative_margin is True


def test_compute_margin_healthy_case():
    sample = BusinessMetricSample(
        scope="merchant-y", period="2026-09", metric_name="transactions", metric_value=1000, cost=200.0, revenue=1000.0
    )
    result = compute_margin(sample)
    assert result is not None
    assert result.gross_margin_pct == pytest.approx(80.0)
    assert result.is_negative_margin is False


def test_flag_negative_margin_scopes_sorts_worst_first():
    samples = [
        BusinessMetricSample(scope="ok", period="p", metric_name="tx", metric_value=100, cost=10.0, revenue=100.0),
        BusinessMetricSample(scope="bad", period="p", metric_name="tx", metric_value=100, cost=900.0, revenue=500.0),
        BusinessMetricSample(scope="worse", period="p", metric_name="tx", metric_value=100, cost=1800.0, revenue=500.0),
        BusinessMetricSample(scope="no-revenue", period="p", metric_name="tx", metric_value=100, cost=50.0, revenue=None),
    ]
    negatives = flag_negative_margin_scopes(samples)
    assert [r.scope for r in negatives] == ["worse", "bad"]


def test_seed_data_produces_at_least_one_negative_margin_scope():
    samples = generate_merchant_samples("2026-09-05")
    negatives = flag_negative_margin_scopes(samples)
    assert len(negatives) >= 1
    assert "merchant-epsilon" in [r.scope for r in negatives]
