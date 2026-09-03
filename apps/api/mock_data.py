"""
Hardcoded demo data so the API returns something real-looking today.

PLACEHOLDER: every function here should eventually read from MongoDB
(and ultimately from live AWS data via the collector service) instead of
returning these constants. Each router calls one of these functions —
swap the body of the function, not the router, and the rest of the app
keeps working.
"""

from packages.schemas.schemas import AgentActivityEntry, ForecastPoint, Resource, SavingsSummary

RESOURCES: list[Resource] = [
    Resource(id="i-0912ab3c4d5e6f701", type="t3.medium", cpu_p95=3, status="Idle", monthly_cost_usd=28.40, tags={"env": "dev"}, owner="sumaira", environment="dev"),
    Resource(id="i-0455cd8e9f0a1b234", type="t3.large", cpu_p95=78, status="Healthy", monthly_cost_usd=61.20, tags={"env": "prod"}, owner="himanshu", environment="prod"),
    Resource(id="i-0a1b2c3d4e5f60789", type="t2.micro", cpu_p95=12, status="Over-provisioned", monthly_cost_usd=8.50, tags={"env": "staging"}, owner="shruti", environment="staging"),
    Resource(id="i-0f9e8d7c6b5a41230", type="m5.large", cpu_p95=91, status="At-risk", monthly_cost_usd=98.10, tags={"env": "prod"}, owner="soham", environment="prod"),
    Resource(id="i-0cafe1234deadbeef", type="t3.small", cpu_p95=45, status="Healthy", monthly_cost_usd=16.80, tags={"env": "dev"}, owner="anay", environment="dev"),
    Resource(id="i-0b00b1e5f00dcafe0", type="t3.medium", cpu_p95=6, status="Idle", monthly_cost_usd=28.40, tags={"env": "dev"}, owner="sumaira", environment="dev"),
]

AGENT_ACTIVITY: list[AgentActivityEntry] = [
    AgentActivityEntry(id="1", agent="Monitor", message="Collected CloudWatch metrics for 47 EC2 instances", timestamp="10:02:14"),
    AgentActivityEntry(id="2", agent="Analyzer", message="Flagged i-0912ab3c4d5e6f701 as idle — CPU 3% avg over 7 days", timestamp="10:02:41"),
    AgentActivityEntry(id="3", agent="Decision", message="Proposed: stop instance i-0912ab3c4d5e6f701 — risk: low", timestamp="10:02:55"),
    AgentActivityEntry(id="4", agent="Supervisor", message="Approved — auto-executing (env=dev, low risk)", timestamp="10:03:02"),
    AgentActivityEntry(id="5", agent="Executor", message="Stopped i-0912ab3c4d5e6f701 — saved $14.20/month", timestamp="10:03:09"),
    AgentActivityEntry(id="6", agent="Supervisor", message="Routed i-0455cd8e9f0a1b234 (env=prod) to human review", timestamp="10:04:18"),
]

FORECAST: list[ForecastPoint] = [
    ForecastPoint(date="Day 1", actual=480),
    ForecastPoint(date="Day 10", actual=505),
    ForecastPoint(date="Day 15", actual=470),
    ForecastPoint(date="Day 20", actual=420),
    ForecastPoint(date="Day 25", actual=395),
    ForecastPoint(date="Day 30", actual=365),
    ForecastPoint(date="Day 35", predicted=350),
    ForecastPoint(date="Day 40", predicted=335),
]

SAVINGS_SUMMARY = SavingsSummary(
    total_monthly_spend=12450,
    wasted_spend_detected=3890,
    wasted_spend_pct=31,
    savings_this_month=2100,
    resources_monitored=47,
)
