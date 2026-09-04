from __future__ import annotations

from .baseline import aggregate_by_dimension
from .schemas import CostBreakdown, CostSample, Contributor


def decompose(
    current: list[CostSample],
    baseline: list[CostSample],
    dimension_key: str,
    *,
    top_n: int = 5,
) -> CostBreakdown:
    """Ranks dimension values by their *absolute* contribution to the
    total delta (not by raw cost) — a value that shrank is just as
    informative as one that grew, and burying it under "top spenders"
    would hide exactly the kind of shift this exists to surface."""
    scope = current[0].scope if current else (baseline[0].scope if baseline else "unknown")

    current_totals = aggregate_by_dimension(current, dimension_key)
    baseline_totals = aggregate_by_dimension(baseline, dimension_key)
    all_keys = set(current_totals) | set(baseline_totals)

    rows = []
    for key in all_keys:
        cur = current_totals.get(key, 0.0)
        base = baseline_totals.get(key, 0.0)
        rows.append((key, base, cur, cur - base))
    rows.sort(key=lambda r: abs(r[3]), reverse=True)

    current_total = sum(current_totals.values())
    baseline_total = sum(baseline_totals.values())
    total_delta = current_total - baseline_total

    top_rows = rows[:top_n]
    attributed_delta = sum(r[3] for r in top_rows)
    unattributed_delta = total_delta - attributed_delta

    def pct_of_delta(delta: float) -> float:
        return round((delta / total_delta * 100) if abs(total_delta) > 1e-9 else 0.0, 2)

    contributors = [
        Contributor(
            dimension_key=dimension_key,
            dimension_value=key,
            baseline_cost=round(base, 4),
            current_cost=round(cur, 4),
            delta=round(delta, 4),
            pct_of_total_delta=pct_of_delta(delta),
        )
        for key, base, cur, delta in top_rows
    ]

    unattributed_pct = pct_of_delta(unattributed_delta)
    attributed_pct = round(100 - unattributed_pct, 1)

    rationale = (
        f"Delta of ₹{total_delta:,.2f} between the baseline and current windows, decomposed by "
        f"'{dimension_key}'. The top {len(contributors)} value(s) account for {attributed_pct:.1f}% of the "
        "change. This is co-occurrence attribution — cost grouped and diffed by tag/dimension — not causal "
        "distributed-trace lineage. Two dimension values moving together does not prove one caused the "
        "other; treat this as a ranked lead for investigation, not a verdict."
    )

    return CostBreakdown(
        scope=scope,
        dimension_key=dimension_key,
        baseline_total=round(baseline_total, 2),
        current_total=round(current_total, 2),
        total_delta=round(total_delta, 2),
        contributors=contributors,
        unattributed_delta=round(unattributed_delta, 2),
        unattributed_pct=unattributed_pct,
        rationale=rationale,
    )
