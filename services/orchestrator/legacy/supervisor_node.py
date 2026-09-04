from typing import Any, TypedDict

from pydantic import ValidationError

from packages.schemas.policy import (
    ActionProposal,
    PolicyDecision,
)
from services.policy.policy_adapter import (
    PolicyAdapter,
)


class SupervisorState(TypedDict, total=False):
    proposals: list[dict[str, Any]]
    policy_decisions: list[dict[str, Any]]
    supervisor_summary: dict[str, int]


def build_supervisor_node(
    policy_adapter: PolicyAdapter,
):
    def supervisor_node(
        state: SupervisorState,
    ) -> SupervisorState:
        raw_proposals = state.get("proposals", [])
        decisions: list[PolicyDecision] = []

        for index, raw_proposal in enumerate(
            raw_proposals
        ):
            try:
                proposal = ActionProposal.model_validate(
                    raw_proposal
                )

                decision = policy_adapter.evaluate(
                    proposal
                )

            except ValidationError:
                proposal_id = str(
                    raw_proposal.get(
                        "proposal_id",
                        f"invalid-{index}",
                    )
                )

                decision = PolicyDecision(
                    proposal_id=proposal_id,
                    outcome="blocked",
                    reason_codes=[
                        "INVALID_PROPOSAL"
                    ],
                    policy_version="validation-v1",
                    simulation_allowed=False,
                    live_execution_allowed=False,
                )

            decisions.append(decision)

        serialized_decisions = [
            decision.model_dump(mode="json")
            for decision in decisions
        ]

        summary = {
            "total": len(decisions),
            "auto_approved": sum(
                decision.outcome == "auto_approved"
                for decision in decisions
            ),
            "human_review": sum(
                decision.outcome == "human_review"
                for decision in decisions
            ),
            "blocked": sum(
                decision.outcome == "blocked"
                for decision in decisions
            ),
        }

        return {
            "policy_decisions": serialized_decisions,
            "supervisor_summary": summary,
        }

    return supervisor_node
