"""
Supervisor Agent (spec section 4.4) — the compliance gatekeeper. Wraps the
deterministic services.policy.engine matrix around each ActionProposal the
Decision Agent produced, translating engine.PolicyResult into the audited
PolicyDecision shape the Executor's SimulatedExecutor requires before it
will act on anything.
"""

from __future__ import annotations

from packages.schemas.policy import ActionProposal, PolicyDecision
from services.policy import engine

_POLICY_VERSION = "policy-engine-v2"


class PolicyAdapter:
    """Safety adapter around the deterministic policy engine — the only
    thing in the pipeline allowed to set `outcome` / `risk_score`."""

    def __init__(self, execution_enabled: bool = False) -> None:
        self.execution_enabled = execution_enabled

    def evaluate(self, proposal: ActionProposal) -> PolicyDecision:
        try:
            result = engine.evaluate(
                environment=proposal.environment,
                risk_level=proposal.risk_level,
                template_id=proposal.action_template,
                has_owner_tag=bool(proposal.parameters.get("has_owner_tag", False)),
                is_protected=bool(proposal.parameters.get("is_protected", False)),
            )
        except Exception:  # noqa: BLE001
            return PolicyDecision(
                proposal_id=proposal.proposal_id,
                outcome="blocked",
                risk_score=1.0,
                reason_codes=["POLICY_ENGINE_ERROR"],
                reason="The policy engine raised evaluating this proposal — blocking as a fail-safe.",
                policy_version=_POLICY_VERSION,
            )

        if not result.approved:
            reason_code = "UNKNOWN_ACTION_TEMPLATE" if "template" in result.reason.lower() else "PROTECTED_RESOURCE"
            return PolicyDecision(
                proposal_id=proposal.proposal_id,
                outcome="blocked",
                risk_score=result.risk_score,
                reason_codes=[reason_code],
                reason=result.reason,
                policy_version=_POLICY_VERSION,
            )

        if result.auto_execute:
            return PolicyDecision(
                proposal_id=proposal.proposal_id,
                outcome="auto_approved",
                risk_score=result.risk_score,
                reason_codes=["LOW_RISK_AUTO_APPROVED"],
                reason=result.reason,
                policy_version=_POLICY_VERSION,
                simulation_allowed=self.execution_enabled,
                live_execution_allowed=False,
            )

        return PolicyDecision(
            proposal_id=proposal.proposal_id,
            outcome="human_review",
            risk_score=result.risk_score,
            reason_codes=["REQUIRES_HUMAN_APPROVAL"],
            reason=result.reason,
            policy_version=_POLICY_VERSION,
        )
