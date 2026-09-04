"""Pure aggregation helpers — no I/O."""

from __future__ import annotations

from .schemas import CostSample


def aggregate_by_dimension(samples: list[CostSample], dimension_key: str) -> dict[str, float]:
    """Sums cost per dimension_value, ignoring any sample whose
    dimension_key doesn't match — callers pass in a mixed list freely."""
    totals: dict[str, float] = {}
    for sample in samples:
        if sample.dimension_key != dimension_key:
            continue
        totals[sample.dimension_value] = totals.get(sample.dimension_value, 0.0) + sample.cost
    return totals
