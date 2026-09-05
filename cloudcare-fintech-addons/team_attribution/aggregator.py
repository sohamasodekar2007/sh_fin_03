from __future__ import annotations

from .schemas import TaggedResourceSample, TeamAttributionReport, TeamCostSummary, UntaggedResource


def _find_tag_value(tags: dict[str, str], tag_key: str) -> str | None:
    """Case-insensitive key match, blank-value-is-absent — 'Team: '
    (empty string) is treated the same as no tag at all, since an empty
    value can't attribute cost to anyone either."""
    lowered_key = tag_key.lower()
    for key, value in (tags or {}).items():
        if key.lower() == lowered_key and value.strip():
            return value.strip()
    return None


def aggregate_by_team(resources: list[TaggedResourceSample], *, tag_key: str = "team") -> TeamAttributionReport:
    """Groups resources by whatever value is found under `tag_key`
    (case-insensitive). A resource with no matching tag is never dropped
    silently or folded into an "Unknown" team bucket that would look like
    a real team — it goes into `untagged_resources`, a distinct
    governance-risk line item, because "cost with no owner" is a
    different finding than "cost owned by a team called Unknown"."""
    teams: dict[str, dict] = {}
    untagged: list[UntaggedResource] = []
    untagged_cost = 0.0
    total_cost = 0.0

    for resource in resources:
        total_cost += resource.monthly_cost
        team_value = _find_tag_value(resource.tags, tag_key)

        if team_value is None:
            untagged.append(
                UntaggedResource(
                    resource_id=resource.resource_id,
                    resource_type=resource.resource_type,
                    monthly_cost=resource.monthly_cost,
                    environment=resource.environment,
                )
            )
            untagged_cost += resource.monthly_cost
            continue

        bucket = teams.setdefault(team_value, {"count": 0, "cost": 0.0, "environments": set()})
        bucket["count"] += 1
        bucket["cost"] += resource.monthly_cost
        if resource.environment:
            bucket["environments"].add(resource.environment)

    team_summaries = [
        TeamCostSummary(
            team=name,
            resource_count=bucket["count"],
            total_monthly_cost=round(bucket["cost"], 2),
            environments=sorted(bucket["environments"]),
        )
        for name, bucket in teams.items()
    ]
    team_summaries.sort(key=lambda t: t.total_monthly_cost, reverse=True)

    untagged_pct = round((untagged_cost / total_cost * 100) if total_cost > 1e-9 else 0.0, 2)
    rationale = (
        f"{len(team_summaries)} team(s) identified via the '{tag_key}' tag (case-insensitive key match, any "
        f"company's own tagging convention). {len(untagged)} resource(s) totaling ₹{untagged_cost:,.2f} "
        f"({untagged_pct:.1f}% of tracked spend) carry no '{tag_key}' tag and cannot be attributed to a team — "
        "a showback/chargeback gap to close, not a bug in this report."
    )

    return TeamAttributionReport(
        tag_key=tag_key,
        teams=team_summaries,
        untagged_resources=untagged,
        untagged_cost=round(untagged_cost, 2),
        untagged_pct=untagged_pct,
        total_cost=round(total_cost, 2),
        rationale=rationale,
    )
