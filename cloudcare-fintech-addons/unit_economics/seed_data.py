"""DEMO-ONLY synthetic data. Never wire this into a real deployment —
it exists so the demo script and the standalone API have something
plausible to show without a live billing/revenue connection. On merge,
replace calls to this with a real query against wherever revenue and
transaction-volume data actually lives."""

from __future__ import annotations

import random

from .schemas import BusinessMetricSample

# (scope, cost_scale, revenue, overhead_range) — cost_scale lets a
# merchant look cheap- or expensive-to-serve per transaction; overhead_range
# is a flat per-period cost floor (e.g. a fixed GPU/LLM risk-scoring
# workload) layered on top. merchant-epsilon's overhead range alone
# exceeds its revenue, so it lands negative-margin *deterministically*
# for any seed/transaction draw — not by getting lucky with random.randint.
_MERCHANT_PROFILES = [
    ("merchant-alpha", 1.00, 40_000.0, (500.0, 3_000.0)),
    ("merchant-beta", 0.55, 18_000.0, (500.0, 3_000.0)),
    ("merchant-gamma", 0.85, 9_000.0, (500.0, 3_000.0)),
    ("merchant-delta", 1.40, 52_000.0, (500.0, 3_000.0)),
    ("merchant-epsilon", 1.00, 6_000.0, (6_500.0, 8_000.0)),
]


def generate_merchant_samples(period: str, *, seed: int = 42) -> list[BusinessMetricSample]:
    rng = random.Random(seed)
    samples = []
    for scope, cost_scale, revenue, overhead_range in _MERCHANT_PROFILES:
        transactions = rng.randint(2_000, 20_000)
        cost = round(transactions * 0.018 * cost_scale + rng.uniform(*overhead_range), 2)
        samples.append(
            BusinessMetricSample(
                scope=scope,
                period=period,
                metric_name="transactions",
                metric_value=transactions,
                cost=cost,
                revenue=revenue,
            )
        )
    return samples
