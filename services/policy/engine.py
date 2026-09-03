"""
Policy engine — the safety guardrails (spec section 4.4, Supervisor Agent).

Not a placeholder: a real, deterministic implementation of the policy
decision matrix, safe to unit test today:

    Condition                                    Auto-execute  Human approval
    env=development/staging, low risk, owned     Yes           Optional
    env=production                               No            Required
    Missing owner/criticality tag                No            Required
    Critical resource / protected tag             No            Blocked
    Action template not in the registry           No            Blocked

The one thing you MUST NOT do as you extend this: never let an LLM's output
override policy_result.approved / risk_score — the Decision agent may
suggest, but only this function decides. services/policy/policy_adapter.py
is the only caller.
"""

from dataclasses import dataclass

KNOWN_TEMPLATES = {"ec2.stop.v1", "ec2.start.v1", "ec2.resize.v1", "ec2.schedule.v1"}

# Continuous risk score inputs (spec section 4.4): < 0.3 -> AUTO_APPROVE,
# >= 0.3 -> REQUIRE_HUMAN. 1.0 is reserved for hard BLOCKED conditions.
_BASE_RISK_BY_ENV = {
    "development": 0.10,
    "staging": 0.35,
    "production": 0.75,
    "unknown": 0.90,
}
_RISK_LEVEL_ADJUSTMENT = {"low": 0.0, "medium": 0.15, "high": 0.30}
_MISSING_OWNER_PENALTY = 0.25


@dataclass
class PolicyResult:
    approved: bool
    auto_execute: bool
    requires_human_approval: bool
    risk_score: float
    reason: str


def compute_risk_score(environment: str, risk_level: str, has_owner_tag: bool) -> float:
    score = _BASE_RISK_BY_ENV.get(environment, _BASE_RISK_BY_ENV["unknown"])
    score += _RISK_LEVEL_ADJUSTMENT.get(risk_level, _RISK_LEVEL_ADJUSTMENT["high"])
    if not has_owner_tag:
        score += _MISSING_OWNER_PENALTY
    return round(min(score, 0.99), 3)  # < 1.0 always — 1.0 is reserved for hard blocks


def evaluate(
    *,
    environment: str,
    risk_level: str,
    template_id: str,
    has_owner_tag: bool,
    is_protected: bool,
) -> PolicyResult:
    if template_id not in KNOWN_TEMPLATES:
        return PolicyResult(False, False, False, 1.0, "Unknown action template — blocked.")

    if is_protected:
        return PolicyResult(False, False, False, 1.0, "Resource is tagged protected — blocked.")

    risk_score = compute_risk_score(environment, risk_level, has_owner_tag)

    if environment == "production":
        return PolicyResult(True, False, True, risk_score, "Production resource — human approval required.")

    if not has_owner_tag:
        return PolicyResult(True, False, True, risk_score, "Missing ownership tag — human approval required.")

    if risk_score < 0.3:
        return PolicyResult(True, True, False, risk_score, "Low-risk dev/staging action — auto-executing.")

    return PolicyResult(True, False, True, risk_score, "Does not meet auto-execute risk threshold — human approval required.")
