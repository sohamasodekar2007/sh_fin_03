from __future__ import annotations

from .schemas import BusinessMetricSample, MarginResult, UnitCostResult


def compute_unit_cost(sample: BusinessMetricSample) -> UnitCostResult:
    """`metric_value` is validated > 0 by the schema — a genuinely
    zero-activity period is a "no data" case the caller must filter out
    before this point, not something this function silently turns into a
    $0 or divide-by-zero unit cost."""
    return UnitCostResult(
        scope=sample.scope,
        period=sample.period,
        metric_name=sample.metric_name,
        cost_per_unit=round(sample.cost / sample.metric_value, 6),
        metric_value=sample.metric_value,
        total_cost=sample.cost,
    )


def compute_margin(sample: BusinessMetricSample, *, negative_margin_threshold_pct: float = 0.0) -> MarginResult | None:
    """None means "can't say" — a scope with no revenue figure gets no
    margin claim at all, rather than one that quietly assumes 0 revenue
    (which would always read as -100% and manufacture a false alarm)."""
    if sample.revenue is None:
        return None

    if sample.revenue <= 0:
        margin_pct = -100.0 if sample.cost > 0 else 0.0
    else:
        margin_pct = round((sample.revenue - sample.cost) / sample.revenue * 100, 2)

    is_negative = margin_pct < negative_margin_threshold_pct
    rationale = (
        f"{sample.scope} in {sample.period}: revenue ₹{sample.revenue:,.2f}, cloud cost ₹{sample.cost:,.2f}, "
        f"gross margin {margin_pct:.1f}%."
    )
    if is_negative:
        rationale += (
            " Below the configured margin floor — flagged for review, not for auto-action. Check "
            "cost_attribution.decompose() for this scope before proposing any pricing or routing change."
        )

    return MarginResult(
        scope=sample.scope,
        period=sample.period,
        revenue=sample.revenue,
        cost=sample.cost,
        gross_margin_pct=margin_pct,
        is_negative_margin=is_negative,
        rationale=rationale,
    )


def flag_negative_margin_scopes(
    samples: list[BusinessMetricSample], *, threshold_pct: float = 0.0
) -> list[MarginResult]:
    """Sorted worst-first. Scopes with no revenue data are silently
    skipped (compute_margin returns None for them) rather than reported
    as "fine" or "negative" — absence of data is neither."""
    results = [compute_margin(s, negative_margin_threshold_pct=threshold_pct) for s in samples]
    negative = [r for r in results if r is not None and r.is_negative_margin]
    negative.sort(key=lambda r: r.gross_margin_pct)
    return negative
