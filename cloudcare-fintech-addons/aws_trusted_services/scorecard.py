from __future__ import annotations

from .schemas import Grade, Pillar, PillarScore, TrustScorecard

_FINDING_PENALTY = 8.0
_CRITICAL_EXTRA_PENALTY = 12.0


def score_pillar(pillar: Pillar, finding_count: int, *, critical_count: int = 0) -> PillarScore:
    """Deliberately simple and auditable: `100 - findings*8 - critical*12`,
    floored at 0. Not a probabilistic/ML risk model — every point lost is
    traceable to a specific counted finding, which matters more here than
    a more "accurate" black-box score nobody can explain to an auditor."""
    if critical_count > finding_count:
        raise ValueError("critical_count cannot exceed finding_count")
    penalty = finding_count * _FINDING_PENALTY + critical_count * _CRITICAL_EXTRA_PENALTY
    score = max(0.0, round(100.0 - penalty, 1))
    rationale = (
        f"{finding_count} finding(s) ({critical_count} critical) — score is 100 minus 8 points per finding and "
        "12 extra points per critical finding, floored at 0. Not a probabilistic risk model."
    )
    return PillarScore(pillar=pillar, score=score, finding_count=finding_count, critical_count=critical_count, rationale=rationale)


def _grade_for(score: float) -> Grade:
    if score >= 90:
        return "A"
    if score >= 75:
        return "B"
    if score >= 60:
        return "C"
    if score >= 40:
        return "D"
    return "F"


def build_scorecard(pillar_inputs: dict[Pillar, tuple[int, int]]) -> TrustScorecard:
    """`pillar_inputs` maps each pillar to (finding_count, critical_count).
    Overall score is the unweighted mean across pillars — simple and
    auditable rather than a weighted composite whose weights would
    themselves need justifying."""
    pillars = [score_pillar(name, count, critical_count=critical) for name, (count, critical) in pillar_inputs.items()]
    overall = round(sum(p.score for p in pillars) / len(pillars), 1) if pillars else 100.0
    grade = _grade_for(overall)
    rationale = (
        f"Overall score {overall} ({grade}) is the unweighted mean across {len(pillars)} pillar(s) — a simple, "
        "auditable aggregate, not a black-box composite risk model."
    )
    return TrustScorecard(pillars=pillars, overall_score=overall, overall_grade=grade, rationale=rationale)
