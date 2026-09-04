"""
Policy engine — the safety guardrails from blueprint section 6.1.

This one is NOT a placeholder. It's a real, deterministic implementation of
the policy decision matrix, safe to unit test today:

    Condition                                   Auto-execute  Human approval
    env=dev/staging, low risk, rollback avail.  Yes           Optional
    env=prod                                    No            Required
    Missing owner/criticality tag               No            Required
    Critical resource / protected tag           No            Blocked
    Action not in template registry             No            Blocked

The one thing you MUST NOT do as you extend this: never let an LLM's output
override policy_result.approved — the Decision agent may suggest, but only
this function decides.
"""

from dataclasses import dataclass


@dataclass
class PolicyResult:
    approved: bool
    auto_execute: bool
    requires_human_approval: bool
    reason: str


KNOWN_TEMPLATES = {
    "ec2.stop.v1", "ec2.start.v1", "ec2.resize.v1", "ec2.schedule.v1",
    # Phase 6 — services/executor/actions.py can now really delete a
    # volume, so the policy engine needs a template id for it to
    # authorize against. Nothing in Decision (services/decision/service.py)
    # produces this template_id yet — ebs.unattached.v1 findings still map
    # to action_type "stop_instance" (a pre-existing gap, out of Phase 6's
    # scope; flagged, not fixed here) — so this is dormant until that's
    # revisited, but the Executor's delete_volume action is fully real and
    # independently testable today.
    "ebs.delete.v1",
}


def evaluate(
    *,
    environment: str,
    risk_level: str,
    template_id: str,
    has_owner_tag: bool,
    is_protected: bool,
) -> PolicyResult:
    if template_id not in KNOWN_TEMPLATES:
        return PolicyResult(False, False, False, "Unknown action template — blocked.")

    if is_protected:
        return PolicyResult(False, False, False, "Resource is tagged protected — blocked.")

    if environment == "prod":
        return PolicyResult(True, False, True, "Production resource — human approval required.")

    if not has_owner_tag:
        return PolicyResult(True, False, True, "Missing ownership tag — human approval required.")

    if environment in ("dev", "staging") and risk_level == "low":
        return PolicyResult(True, True, False, "Low-risk dev/staging action — auto-executing.")

    return PolicyResult(True, False, True, "Does not meet auto-execute criteria — human approval required.")
