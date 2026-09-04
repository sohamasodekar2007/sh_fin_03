from typing import Any, TypedDict

from pydantic import ValidationError

from packages.schemas.policy import (
    ActionProposal,
    PolicyDecision,
)
from services.executor.simulated_executor import (
    SimulatedExecutor,
)


class ExecutorState(TypedDict, total=False):
    proposals: list[dict[str, Any]]
    policy_decisions: list[dict[str, Any]]
    execution_records: list[dict[str, Any]]
    execution_summary: dict[str, int]


def build_executor_node(
    executor: SimulatedExecutor,
):
    def executor_node(
        state: ExecutorState,
    ) -> ExecutorState:
        raw_proposals = state.get("proposals", [])
        raw_decisions = state.get(
            "policy_decisions",
            [],
        )

        proposals_by_id: dict[
            str,
            ActionProposal,
        ] = {}

        for raw_proposal in raw_proposals:
            try:
                proposal = ActionProposal.model_validate(
                    raw_proposal
                )

                proposals_by_id[
                    proposal.proposal_id
                ] = proposal

            except ValidationError:
                continue

        execution_records = []

        for raw_decision in raw_decisions:
            try:
                decision = PolicyDecision.model_validate(
                    raw_decision
                )
            except ValidationError:
                continue

            proposal = proposals_by_id.get(
                decision.proposal_id
            )

            if proposal is None:
                continue

            record = executor.execute(
                proposal=proposal,
                decision=decision,
            )

            execution_records.append(
                record.model_dump(mode="json")
            )

        summary = {
            "total": len(execution_records),
            "simulated": sum(
                record["status"] == "simulated"
                for record in execution_records
            ),
            "disabled": sum(
                record["status"] == "disabled"
                for record in execution_records
            ),
            "blocked": sum(
                record["status"] == "blocked"
                for record in execution_records
            ),
            "actual_aws_calls": sum(
                int(record["actual_aws_call_made"])
                for record in execution_records
            ),
        }

        return {
            "execution_records": execution_records,
            "execution_summary": summary,
        }

    return executor_node
