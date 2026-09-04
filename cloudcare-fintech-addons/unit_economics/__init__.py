"""MarginOS-lite: cost-per-unit and gross-margin calculations, scoped to
a business dimension (merchant, customer, plan, ...).

Closes a real gap: sh_fin_03/CDW_HACKATHON_PITCH.md already pitches
"Unit Economics & Margin Analytics" as feature #4, but no service in the
main repo backs that claim yet. This package is that backing.
"""

from .engine import compute_margin, compute_unit_cost, flag_negative_margin_scopes
from .schemas import BusinessMetricSample, MarginResult, UnitCostResult

__all__ = [
    "compute_unit_cost",
    "compute_margin",
    "flag_negative_margin_scopes",
    "BusinessMetricSample",
    "UnitCostResult",
    "MarginResult",
]
