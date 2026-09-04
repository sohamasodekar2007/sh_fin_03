from hashlib import sha256

from services.executor.execution_audit import (
    ExecutionAuditRepository,
)
from packages.schemas.execution import ExecutionRecord
from packages.schemas.policy import (
    ActionProposal,
    PolicyDecision,
)


class SimulatedExecutor:
    SUPPORTED_TEMPLATES = {
        "ec2.stop.v1",
    }

    def __init__(
        self,
        audit_repository: ExecutionAuditRepository,
        execution_enabled: bool = False,
        execution_mode: str = "simulation",
    ) -> None:
        if execution_mode != "simulation":
            raise ValueError(
                "CloudCare supports simulation mode only"
            )

        self.audit_repository = audit_repository
        self.execution_enabled = execution_enabled
        self.execution_mode = execution_mode

    @staticmethod
    def build_idempotency_key(
        proposal: ActionProposal,
    ) -> str:
        raw_key = (
            f"{proposal.tenant_id}:"
            f"{proposal.proposal_id}:"
            f"{proposal.resource_id}:"
            f"{proposal.action_template}"
        )

        return sha256(
            raw_key.encode("utf-8")
        ).hexdigest()

    def _record(
        self,
        proposal: ActionProposal,
        decision: PolicyDecision,
        idempotency_key: str,
        status: str,
        reason_codes: list[str],
        would_execute: dict | None = None,
        verification: dict | None = None,
    ) -> ExecutionRecord:
        record = ExecutionRecord(
            idempotency_key=idempotency_key,
            proposal_id=proposal.proposal_id,
            tenant_id=proposal.tenant_id,
            resource_id=proposal.resource_id,
            resource_type=proposal.resource_type,
            environment=proposal.environment,
            action_template=proposal.action_template,
            status=status,
            reason_codes=reason_codes,
            policy_version=decision.policy_version,
            would_execute=would_execute or {},
            actual_aws_call_made=False,
            verification=verification or {
                "verified": True,
                "aws_state_changed": False,
                "mode": "simulation",
            },
        )

        return self.audit_repository.save(record)

    def execute(
        self,
        proposal: ActionProposal,
        decision: PolicyDecision,
    ) -> ExecutionRecord:
        idempotency_key = self.build_idempotency_key(
            proposal
        )

        existing = (
            self.audit_repository
            .get_by_idempotency_key(idempotency_key)
        )

        if existing is not None:
            return existing

        # VPS is read-only in this build — there is no billing API to
        # verify a stop actually happened against, and stopping a VM on a
        # company-owned box via SSH has a much worse failure mode than
        # ec2:StopInstances (no API to reverse it, no console to recover
        # from). Extension point for real VPS execution (virsh shutdown /
        # docker stop), once that's built and reviewed:
        #   services/executor/vps_actions.py (does not exist yet, on purpose)
        if proposal.provider == "vps":
            return self._record(
                proposal=proposal,
                decision=decision,
                idempotency_key=idempotency_key,
                status="blocked",
                reason_codes=["vps_execution_not_enabled"],
            )

        if decision.proposal_id != proposal.proposal_id:
            return self._record(
                proposal=proposal,
                decision=decision,
                idempotency_key=idempotency_key,
                status="blocked",
                reason_codes=[
                    "PROPOSAL_DECISION_MISMATCH"
                ],
            )

        if (
            proposal.action_template
            not in self.SUPPORTED_TEMPLATES
        ):
            return self._record(
                proposal=proposal,
                decision=decision,
                idempotency_key=idempotency_key,
                status="blocked",
                reason_codes=[
                    "UNSUPPORTED_ACTION_TEMPLATE"
                ],
            )

        if proposal.environment == "production":
            return self._record(
                proposal=proposal,
                decision=decision,
                idempotency_key=idempotency_key,
                status="blocked",
                reason_codes=[
                    "PRODUCTION_EXECUTION_BLOCKED"
                ],
            )

        if decision.live_execution_allowed:
            return self._record(
                proposal=proposal,
                decision=decision,
                idempotency_key=idempotency_key,
                status="blocked",
                reason_codes=[
                    "LIVE_EXECUTION_FORBIDDEN"
                ],
            )

        if decision.outcome != "auto_approved":
            return self._record(
                proposal=proposal,
                decision=decision,
                idempotency_key=idempotency_key,
                status="blocked",
                reason_codes=[
                    "PROPOSAL_NOT_AUTO_APPROVED"
                ],
            )

        if (
            not self.execution_enabled
            or not decision.simulation_allowed
        ):
            return self._record(
                proposal=proposal,
                decision=decision,
                idempotency_key=idempotency_key,
                status="disabled",
                reason_codes=[
                    "EXECUTION_KILL_SWITCH_ACTIVE"
                ],
            )

        would_execute = {
            "provider": "aws",
            "service": "ec2",
            "operation": "StopInstances",
            "parameters": {
                "InstanceIds": [
                    proposal.resource_id
                ]
            },
            "simulation": True,
            "message": (
                "CloudCare would request an EC2 stop "
                "operation. No AWS API call was made."
            ),
        }

        verification = {
            "verified": True,
            "mode": "simulation",
            "aws_state_changed": False,
            "actual_aws_call_made": False,
            "expected_result": (
                "Instance state remains unchanged"
            ),
        }

        return self._record(
            proposal=proposal,
            decision=decision,
            idempotency_key=idempotency_key,
            status="simulated",
            reason_codes=[
                "SIMULATION_COMPLETED"
            ],
            would_execute=would_execute,
            verification=verification,
        )
