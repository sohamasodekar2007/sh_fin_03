"""
Cost Explorer collector — real boto3 implementation.

Cost Explorer is a global (us-east-1) endpoint and its data can lag several
hours behind CloudWatch — callers should treat `get_cost_and_usage` as
best-effort and fall back to an estimated-cost heuristic for live demos.
"""

from __future__ import annotations

from typing import Any


def get_cost_and_usage(session, start_date: str, end_date: str) -> list[dict[str, Any]]:
    ce = session.client("ce", region_name="us-east-1")
    response = ce.get_cost_and_usage(
        TimePeriod={"Start": start_date, "End": end_date},
        Granularity="DAILY",
        Metrics=["UnblendedCost"],
        GroupBy=[{"Type": "DIMENSION", "Key": "SERVICE"}],
    )
    results: list[dict[str, Any]] = []
    for period in response.get("ResultsByTime", []):
        date = period["TimePeriod"]["Start"]
        for group in period.get("Groups", []):
            results.append(
                {
                    "date": date,
                    "service": group["Keys"][0],
                    "amount": float(group["Metrics"]["UnblendedCost"]["Amount"]),
                    "unit": group["Metrics"]["UnblendedCost"]["Unit"],
                }
            )
    return results
