from collections.abc import Callable, Mapping
from typing import Any

from packages.schemas.policy import (
    ActionProposal,
    PolicyDecision,
)


PolicyEvaluator = Callable[
    [dict[str, Any]],
    Mapping[str, Any],
]


class PolicyAdapter:
    """
    Safety adapter around the existing deterministic policy engine.
    """

    ALLOWED_ACTION_TEMPLATES = {
        "ec2.stop.v1",
        "ec2.start.v1",
        "ec2.resize.v1",
        "ec2.schedule.v1",
        "ebs.delete.v1",
        # Phase 15
        "asg.adjust_capacity.v1",
        "ec2.no_action.v1",
    }

    def __init__(
        self,
        evaluator: PolicyEvaluator,
        execution_enabled: bool = False,
        execution_mode: str = "simulation",
    ) -> None:
        if execution_mode != "simulation":
            raise ValueError(
                "Only simulation mode is supported"
            )

        self.evaluator = evaluator
        self.execution_enabled = execution_enabled
        self.execution_mode = execution_mode

    @staticmethod
    def _normalize_reason_codes(
        raw_reasons: Any,
    ) -> list[str]:
        if isinstance(raw_reasons, str):
            return [raw_reasons]

        if isinstance(raw_reasons, list):
            return [
                str(reason)
                for reason in raw_reasons
            ]

        return []

    @staticmethod
    def _decision(
        proposal: ActionProposal,
        outcome: str,
        reason_codes: list[str],
        policy_version: str,
        simulation_allowed: bool = False,
    ) -> PolicyDecision:
        return PolicyDecision(
            proposal_id=proposal.proposal_id,
            outcome=outcome,
            reason_codes=reason_codes,
            policy_version=policy_version,
            simulation_allowed=simulation_allowed,
            live_execution_allowed=False,
        )

    def evaluate(
        self,
        proposal: ActionProposal,
    ) -> PolicyDecision:
        if (
            proposal.action_template
            not in self.ALLOWED_ACTION_TEMPLATES
        ):
            return self._decision(
                proposal=proposal,
                outcome="blocked",
                reason_codes=[
                    "UNKNOWN_ACTION_TEMPLATE"
                ],
                policy_version="adapter-v1",
            )

        try:
            engine_result = dict(
                self.evaluator(
                    proposal.model_dump(mode="json")
                )
            )
        except Exception:
            return self._decision(
                proposal=proposal,
                outcome="blocked",
                reason_codes=[
                    "POLICY_ENGINE_ERROR"
                ],
                policy_version="adapter-v1",
            )

        allowed = bool(
            engine_result.get("allowed", False)
        )

        requires_human_review = bool(
            engine_result.get(
                "requires_human_review",
                True,
            )
        )

        reason_codes = self._normalize_reason_codes(
            engine_result.get("reason_codes")
        )

        policy_version = str(
            engine_result.get(
                "policy_version",
                "existing-policy",
            )
        )

        if not allowed:
            return self._decision(
                proposal=proposal,
                outcome="blocked",
                reason_codes=reason_codes
                or ["POLICY_DENIED"],
                policy_version=policy_version,
            )

        if proposal.environment == "production":
            return self._decision(
                proposal=proposal,
                outcome="human_review",
                reason_codes=reason_codes
                + ["PRODUCTION_REQUIRES_HUMAN"],
                policy_version=policy_version,
            )

        if proposal.environment != "development":
            return self._decision(
                proposal=proposal,
                outcome="human_review",
                reason_codes=reason_codes
                + ["NON_DEV_REQUIRES_HUMAN"],
                policy_version=policy_version,
            )

        if proposal.risk_level != "low":
            return self._decision(
                proposal=proposal,
                outcome="human_review",
                reason_codes=reason_codes
                + ["RISK_REQUIRES_HUMAN"],
                policy_version=policy_version,
            )

        if requires_human_review:
            return self._decision(
                proposal=proposal,
                outcome="human_review",
                reason_codes=reason_codes
                or ["POLICY_REQUIRES_HUMAN"],
                policy_version=policy_version,
            )

        return self._decision(
            proposal=proposal,
            outcome="auto_approved",
            reason_codes=reason_codes
            or ["LOW_RISK_DEV_APPROVED"],
            policy_version=policy_version,
            simulation_allowed=self.execution_enabled,
        )
