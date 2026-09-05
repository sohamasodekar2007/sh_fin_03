"""Shared synthetic scenario builders, used by both run_demo.py (CLI) and
api/main.py (the standalone FastAPI demo endpoints), so the two stay
consistent. Every function here is clearly DEMO/SYNTHETIC data — see each
package's own seed_data/honesty notes for why this must never be mistaken
for a real feed."""

from __future__ import annotations

import random
import time
from datetime import datetime, timedelta, timezone

from cost_attribution import CostSample
from spend_velocity.schemas import SpendSample
from unit_economics.seed_data import generate_merchant_samples

SCENARIO_NOW = datetime(2026, 9, 5, 9, 0, tzinfo=timezone.utc)
SPIKED_SCOPE = "risk-analysis-agent"
SPIKE_MERCHANT = "M-4082"


def _live_anchor(bucket_seconds: int = 15) -> tuple[datetime, int]:
    """When a caller wants a "live" feed rather than the fixed scenario
    instant, anchor `now` to the real wall clock and reseed noise off a
    coarse time bucket. This isn't fake randomness dressed up as live data
    — it's the same deterministic scenario formula, just re-evaluated with
    a moving `now` and a seed that ticks forward every `bucket_seconds`,
    so polling the demo endpoint every 15s genuinely produces a slightly
    different (but reproducible-within-the-bucket) reading, the way a real
    noisy telemetry feed would."""
    now = datetime.now(timezone.utc)
    seed = int(time.time() // bucket_seconds)
    return now, seed


def _samples_for_window(scope, start, end, interval_minutes, hourly_rate, noise_frac, rng, tags):
    samples = []
    t = start
    per_sample_mean = hourly_rate * (interval_minutes / 60.0)
    while t < end:
        cost = max(0.0, rng.gauss(per_sample_mean, per_sample_mean * noise_frac))
        samples.append(SpendSample(scope=scope, timestamp=t, estimated_cost=round(cost, 4), is_production=True, tags=tags))
        t += timedelta(minutes=interval_minutes)
    return samples


def build_spend_spike_scenario(
    *, now: datetime | None = None, seed: int = 11, live: bool = False
) -> list[SpendSample]:
    """A recursive risk-analysis agent retry storm: ~7 days flat at
    ₹500/hr, then the last 2 hours jump to ~12x that — modeled after the
    incident narrative in the SpendShield pitch. `live=True` anchors the
    window to the real wall clock instead of the fixed SCENARIO_NOW, for
    a dashboard that's meant to look like it's polling something live."""
    if live:
        now, seed = _live_anchor()
    else:
        now = now or SCENARIO_NOW
    rng = random.Random(seed)
    tags = {"cloudcare:environment": "production", "team": "risk"}
    baseline = _samples_for_window(
        SPIKED_SCOPE, now - timedelta(hours=168), now - timedelta(hours=2), 30, 500.0, 0.08, rng, tags
    )
    spike = _samples_for_window(
        SPIKED_SCOPE, now - timedelta(hours=2), now, 30, 6_200.0, 0.10, rng, tags
    )
    return baseline + spike


def build_spend_spike_period_rates(*, live: bool = False) -> tuple[list[float], list[float]]:
    """Coarser hourly-rate series for the CUSUM confirmation step — kept
    separate from the raw SpendSample feed since a real deployment would
    likely compute these from a rollup table, not by re-bucketing raw
    samples every time."""
    seed = _live_anchor()[1] if live else 11
    rng = random.Random(seed)
    baseline_rates = [round(rng.gauss(500.0, 40.0), 2) for _ in range(24)]
    current_rates = [round(rng.gauss(6_200.0, 250.0), 2) for _ in range(4)]
    return baseline_rates, current_rates


def build_spend_spike_hourly_series(
    *, now: datetime | None = None, seed: int = 11, live: bool = False, hours_back: int = 30
) -> list[dict]:
    """Buckets the same underlying SpendSample scenario into hourly
    totals for charting — real aggregation of the scenario data, not a
    separately-fabricated curve, so the sparkline and the alert numbers
    it sits next to can never silently disagree."""
    if live:
        now, seed = _live_anchor()
    else:
        now = now or SCENARIO_NOW
    samples = build_spend_spike_scenario(now=now, seed=seed)
    points = []
    for offset in range(hours_back, 0, -1):
        start = now - timedelta(hours=offset)
        end = now - timedelta(hours=offset - 1)
        bucket_cost = sum(s.estimated_cost for s in samples if start <= s.timestamp < end)
        points.append(
            {
                "hours_ago": offset - 1,
                "label": "now" if offset == 1 else f"-{offset - 1}h",
                "cost": round(bucket_cost, 2),
                "phase": "current" if offset <= 2 else "baseline",
            }
        )
    return points


def build_cost_attribution_scenario() -> tuple[list[CostSample], list[CostSample]]:
    """Baseline vs current per-merchant cost for the same spike window —
    M-4082 is engineered to explain ~93% of the delta, matching the
    "who's burning the money" narrative."""
    baseline_costs = {
        "M-1001": 120.0,
        "M-2044": 95.0,
        "M-3070": 80.0,
        SPIKE_MERCHANT: 60.0,
        "M-5511": 45.0,
    }
    current_costs = {
        "M-1001": 130.0,
        "M-2044": 100.0,
        "M-3070": 85.0,
        SPIKE_MERCHANT: 1_180.0,
        "M-5511": 48.0,
    }
    baseline = [CostSample(scope=SPIKED_SCOPE, dimension_key="merchant", dimension_value=k, cost=v) for k, v in baseline_costs.items()]
    current = [CostSample(scope=SPIKED_SCOPE, dimension_key="merchant", dimension_value=k, cost=v) for k, v in current_costs.items()]
    return current, baseline


def build_unit_economics_scenario(period: str = "2026-09-05"):
    return generate_merchant_samples(period)


def build_daily_cost_history(*, days: int = 21, seed: int = 5) -> list[dict]:
    """21 days of daily cost, flat-ish with weekday seasonality, ending in
    a genuine spike on the final day — same "recursive retry storm"
    narrative as the spend-velocity scenario, but at daily granularity so
    ForecastAnomalyGuard's walk-forward evaluation has something real to
    flag on the last day without leaking that spike into its own forecast."""
    rng = random.Random(seed)
    start = SCENARIO_NOW.date() - timedelta(days=days - 1)
    points = []
    for i in range(days):
        d = start + timedelta(days=i)
        is_weekend = d.weekday() >= 5
        base = 850.0 if is_weekend else 1_000.0
        cost = max(0.0, rng.gauss(base, base * 0.06))
        if i == days - 1:
            cost *= 1.8  # the day the anomaly guard should catch
        points.append({"date": d.isoformat(), "actual_cost": round(cost, 2)})
    return points


def build_team_attribution_scenario() -> list[dict]:
    """Five resources across three teams, plus two deliberately untagged
    ones — the "governance gap" the report's own rationale calls out."""
    return [
        {"resource_id": "i-081a", "resource_type": "ec2", "environment": "production", "monthly_cost": 420.0, "tags": {"team": "payments", "Environment": "production"}},
        {"resource_id": "i-0c3f", "resource_type": "ec2", "environment": "staging", "monthly_cost": 90.0, "tags": {"Team": "payments", "Environment": "staging"}},
        {"resource_id": "db-risk-1", "resource_type": "rds", "environment": "production", "monthly_cost": 610.0, "tags": {"team": "risk", "Environment": "production"}},
        {"resource_id": "bucket-analytics", "resource_type": "s3", "environment": "production", "monthly_cost": 75.0, "tags": {"team": "analytics"}},
        {"resource_id": "i-0f91-legacy", "resource_type": "ec2", "environment": "production", "monthly_cost": 260.0, "tags": {}},
        {"resource_id": "vol-orphaned", "resource_type": "ebs_volume", "environment": None, "monthly_cost": 38.0, "tags": {"Owner": "unknown"}},
    ]


def build_trusted_services_scenario() -> tuple[list[dict], list[str]]:
    """Approved list matches a typical mid-size fintech's real footprint;
    Redshift and a lone EMR cluster are the deliberate "shadow IT" cases."""
    usage = [
        {"service": "ec2", "resource_count": 42, "monthly_cost": 3_200.0},
        {"service": "rds", "resource_count": 6, "monthly_cost": 1_850.0},
        {"service": "s3", "resource_count": 18, "monthly_cost": 410.0},
        {"service": "lambda", "resource_count": 30, "monthly_cost": 190.0},
        {"service": "redshift", "resource_count": 1, "monthly_cost": 2_400.0},
        {"service": "emr", "resource_count": 1, "monthly_cost": 980.0},
    ]
    approved_services = ["ec2", "rds", "s3", "lambda", "cloudwatch", "iam"]
    return usage, approved_services


def build_security_policy_addons_scenario() -> dict:
    """Deliberately a mix: some clean, some flagged, across all four
    checks — so the demo shows both "found nothing" and "found something"
    states, not just a wall of findings."""
    return {
        "security_group_rules": [
            {"security_group_id": "sg-web", "port": 22, "protocol": "tcp", "cidr": "0.0.0.0/0"},
            {"security_group_id": "sg-db", "port": 5432, "protocol": "tcp", "cidr": "10.0.4.0/24"},
            {"security_group_id": "sg-legacy", "port": 3389, "protocol": "tcp", "cidr": "0.0.0.0/0"},
        ],
        "storage_resources": [
            {"resource_id": "vol-0a1b", "resource_type": "ebs_volume", "encrypted": True},
            {"resource_id": "db-legacy-1", "resource_type": "rds_instance", "encrypted": False},
        ],
        "s3_buckets": [
            {"bucket": "cloudcare-assets", "public_access_block_enabled": True, "acl_is_public": False},
            {"bucket": "cloudcare-exports-legacy", "public_access_block_enabled": False, "acl_is_public": False},
        ],
        "access_keys": [
            {"principal_name": "svc-ingest", "access_key_id": "AKIA-INGEST", "age_days": 40},
            {"principal_name": "ops.jsmith", "access_key_id": "AKIA-JSMITH", "age_days": 210},
        ],
    }
