"""Severity -> containment-action mapping. Pure functions, mirrors the
"production can never silently auto-execute" rule already enforced in
sh_fin_03/services/policy/engine.py, and reuses the same
cloudcare:exclude / cloudcare:max-risk tag conventions via
`_tags_shim.py` (see that file's docstring for the merge step)."""

from __future__ import annotations

from ._tags_shim import exceeds_max_risk, is_excluded
from .schemas import ContainmentAction, Severity

_ACTION_BY_SEVERITY: dict[Severity, ContainmentAction] = {
    "low": "monitor_only",
    "medium": "alert_only",
    "high": "throttle_non_prod",
    "critical": "escalate_supervisor",
}


def decide_containment(
    severity: Severity, *, is_production: bool, tags: dict[str, str]
) -> tuple[ContainmentAction, bool]:
    """Returns (action, requires_human_approval). Never returns an action
    that would auto-throttle a production scope — that always escalates
    to a human instead, same floor the main policy engine draws for
    execution proposals."""
    if is_excluded(tags):
        # An explicit opt-out still gets *surfaced*, just never acted on.
        return "monitor_only", True

    action = _ACTION_BY_SEVERITY[severity]
    requires_human_approval = action in ("escalate_supervisor", "block_auto_execute")

    if is_production and action == "throttle_non_prod":
        action = "escalate_supervisor"
        requires_human_approval = True

    if exceeds_max_risk(severity, tags):
        requires_human_approval = True
        if action in ("monitor_only", "alert_only", "throttle_non_prod"):
            action = "escalate_supervisor"

    return action, requires_human_approval
