"""DollarTrace-lite: cost-delta attribution without needing distributed
tracing infrastructure.

Given two sets of cost samples (a baseline window and a current window),
each tagged with a dimension (merchant, service, region, tag:team, ...),
`decompose()` answers "which values of this dimension explain the change
in total cost" — a cost flame-graph's ranking, without requiring
OpenTelemetry spans across every service in the transaction path.

Deliberately scoped down from the full DollarTrace concept (per-span
`finops.estimated_cost` on OpenTelemetry traces): this only needs cost
samples you can already get from Cost Explorer/CUR tag breakdowns or
CloudWatch dimensions, not new instrumentation. See ../MERGE_GUIDE.md for
the upgrade path if/when real trace-level attribution is wanted later.
"""

from .breakdown import decompose
from .schemas import CostBreakdown, CostSample, Contributor

__all__ = ["decompose", "CostSample", "Contributor", "CostBreakdown"]
