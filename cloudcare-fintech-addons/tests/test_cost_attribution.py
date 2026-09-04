from __future__ import annotations

from cost_attribution import CostSample, decompose


def _sample(scope, value, cost, dimension_key="merchant"):
    return CostSample(scope=scope, dimension_key=dimension_key, dimension_value=value, cost=cost)


def test_decompose_identifies_dominant_contributor():
    baseline = [
        _sample("risk-agent", "M-1001", 120.0),
        _sample("risk-agent", "M-2044", 95.0),
        _sample("risk-agent", "M-4082", 60.0),
    ]
    current = [
        _sample("risk-agent", "M-1001", 130.0),
        _sample("risk-agent", "M-2044", 100.0),
        _sample("risk-agent", "M-4082", 1180.0),
    ]
    breakdown = decompose(current, baseline, "merchant")

    assert breakdown.scope == "risk-agent"
    assert breakdown.contributors[0].dimension_value == "M-4082"
    assert breakdown.contributors[0].delta > 1000
    assert breakdown.total_delta == round((130 + 100 + 1180) - (120 + 95 + 60), 2)


def test_decompose_handles_new_dimension_value_not_in_baseline():
    baseline = [_sample("svc", "region-a", 50.0, dimension_key="region")]
    current = [
        _sample("svc", "region-a", 55.0, dimension_key="region"),
        _sample("svc", "region-b", 200.0, dimension_key="region"),
    ]
    breakdown = decompose(current, baseline, "region")

    values = {c.dimension_value: c for c in breakdown.contributors}
    assert values["region-b"].baseline_cost == 0.0
    assert values["region-b"].delta == 200.0


def test_decompose_handles_no_change():
    baseline = [_sample("svc", "a", 10.0), _sample("svc", "b", 20.0)]
    current = [_sample("svc", "a", 10.0), _sample("svc", "b", 20.0)]
    breakdown = decompose(current, baseline, "merchant")

    assert breakdown.total_delta == 0.0
    assert breakdown.unattributed_pct == 0.0
    for contributor in breakdown.contributors:
        assert contributor.delta == 0.0


def test_decompose_top_n_limits_contributors_and_tracks_unattributed():
    baseline = [_sample("svc", str(i), 10.0) for i in range(10)]
    current = [_sample("svc", str(i), 10.0 + i * 5) for i in range(10)]
    breakdown = decompose(current, baseline, "merchant", top_n=3)

    assert len(breakdown.contributors) == 3
    assert breakdown.unattributed_delta > 0
    assert breakdown.rationale  # always non-empty, always states the caveat
    assert "co-occurrence" in breakdown.rationale
