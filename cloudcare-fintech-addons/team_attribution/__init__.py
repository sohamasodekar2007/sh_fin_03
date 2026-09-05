"""AWS tag-based team/ownership cost attribution — "any team working on
AWS, at any company, shown by tags." Deliberately company-agnostic: the
tag key that identifies a team varies (Team, team, CostCenter, Owner...),
so the tag key is a caller-supplied parameter with case-insensitive
matching, not a hardcoded convention.

Distinct from services/governance/tags.py's has_missing_ownership (which
only checks tag *presence* for a single resource) — this aggregates cost
*across* resources, grouped by tag value, and surfaces the untagged
remainder as its own governance-risk line item rather than silently
dropping it.
"""

from .aggregator import aggregate_by_team
from .schemas import TaggedResourceSample, TeamAttributionReport, TeamCostSummary, UntaggedResource

__all__ = [
    "aggregate_by_team",
    "TaggedResourceSample",
    "TeamCostSummary",
    "UntaggedResource",
    "TeamAttributionReport",
]
