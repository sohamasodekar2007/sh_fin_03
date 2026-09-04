"""Run with: python -m demo.run_demo (from the cloudcare-fintech-addons
folder, using an interpreter that has pydantic installed — the main
repo's .venv already does).

Walks through the three-scene narrative from the pitch: a spend spike is
detected before billing data would show it (SpendShield-lite), the spike
is attributed to the merchant driving it (DollarTrace-lite), and the
margin impact on that merchant's economics is surfaced (MarginOS-lite).
Every number printed here comes from synthetic scenario data — see
demo/scenario.py — not from a real cloud account.
"""

from __future__ import annotations

import sys

# Windows terminals often default to a cp1252 console that can't encode
# the currency symbol in the rationale strings — force UTF-8 so this runs
# the same on Windows, macOS, and Linux without downgrading the text.
try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

from cost_attribution import decompose
from spend_velocity.guard import SpendVelocityGuard
from spend_velocity.notify import NullNotificationSink
from unit_economics.engine import compute_margin, flag_negative_margin_scopes

from demo.scenario import (
    SCENARIO_NOW,
    build_cost_attribution_scenario,
    build_spend_spike_period_rates,
    build_spend_spike_scenario,
    build_unit_economics_scenario,
)


def _rule():
    print("-" * 72)


def main() -> None:
    print("=" * 72)
    print("CloudCare fintech add-ons — synthetic demo (no real cloud data)")
    print("=" * 72)

    # Scene 1: SpendShield-lite catches the incident
    _rule()
    print("SCENE 1 — Spend Velocity Guard (SpendShield-lite)")
    _rule()
    samples = build_spend_spike_scenario()
    baseline_rates, current_rates = build_spend_spike_period_rates()
    guard = SpendVelocityGuard(notification_sink=NullNotificationSink())
    alert = guard.evaluate(
        samples,
        is_production=True,
        now=SCENARIO_NOW,
        baseline_period_rates=baseline_rates,
        current_period_rates=current_rates,
    )
    if alert is None:
        print("No alert raised (unexpected for this scenario).")
    else:
        print(f"ALERT [{alert.severity.upper()}] scope={alert.scope}")
        print(f"  current: Rs {alert.reading.current_hourly_rate:,.2f}/hr  baseline: Rs {alert.reading.baseline_hourly_rate:,.2f}/hr")
        print(f"  projected 24h cost if unaddressed: Rs {alert.projected_24h_cost:,.2f}")
        print(f"  recommended action: {alert.recommended_action}  (human approval required: {alert.requires_human_approval})")
        print(f"  rationale: {alert.rationale}")

    # Scene 2: DollarTrace-lite explains why
    _rule()
    print("SCENE 2 — Cost Attribution (DollarTrace-lite)")
    _rule()
    current, baseline = build_cost_attribution_scenario()
    breakdown = decompose(current, baseline, "merchant")
    print(f"Total delta: Rs {breakdown.total_delta:,.2f} across '{breakdown.dimension_key}'")
    for contributor in breakdown.contributors:
        print(
            f"  {contributor.dimension_value:>8}: Rs {contributor.baseline_cost:>9,.2f} -> Rs {contributor.current_cost:>9,.2f}"
            f"  (delta Rs {contributor.delta:>9,.2f}, {contributor.pct_of_total_delta:>6.1f}% of total change)"
        )
    print(f"  rationale: {breakdown.rationale}")

    # Scene 3: MarginOS-lite shows the business impact
    _rule()
    print("SCENE 3 — Unit Economics (MarginOS-lite)")
    _rule()
    merchant_samples = build_unit_economics_scenario()
    for sample in merchant_samples:
        margin = compute_margin(sample)
        flag = " <-- NEGATIVE MARGIN" if margin and margin.is_negative_margin else ""
        if margin:
            print(f"  {sample.scope:>16}: revenue Rs {margin.revenue:>9,.2f}  cost Rs {margin.cost:>9,.2f}  margin {margin.gross_margin_pct:>6.1f}%{flag}")
    negatives = flag_negative_margin_scopes(merchant_samples)
    if negatives:
        _rule()
        print(f"{len(negatives)} scope(s) flagged for review (worst first):")
        for result in negatives:
            print(f"  - {result.rationale}")

    _rule()
    print("Done. Every number above is synthetic — see demo/scenario.py.")


if __name__ == "__main__":
    main()
