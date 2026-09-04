"""SpendShield-lite: a real-time spend-velocity circuit breaker.

Standalone package — see ../MERGE_GUIDE.md for exactly how each file maps
into sh_fin_03/services/ when you're ready to fold this in. Nothing here
imports from sh_fin_03; `_tags_shim.py` is a deliberate, marked duplicate
of services/governance/tags.py's helpers so this package runs on its own
until merge time.

Honesty note carried through this whole package: nothing here reads real
AWS billing data. AWS Cost Explorer/Budgets update on an 8-24h delay —
that lag is the entire reason this package exists — so "spend" always
means an *estimated* cost derived from whatever CloudWatch usage-metric
proxy (or other feed) you wire into `SpendSample`, never an actual billed
dollar figure. Every alert's rationale says this explicitly.
"""

from .guard import SpendVelocityGuard
from .schemas import ContainmentAction, Severity, SpendSample, VelocityAlert, VelocityReading

__all__ = [
    "SpendVelocityGuard",
    "SpendSample",
    "VelocityReading",
    "VelocityAlert",
    "Severity",
    "ContainmentAction",
]
