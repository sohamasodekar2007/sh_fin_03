"""
Pure functions, no AWS calls — cloudcare:* tag conventions shared across
the Analyzer, Decision, Supervisor, and Phase 14's RDS/S3 advisors.
"""

from __future__ import annotations

from typing import Literal

RiskLevel = Literal["low", "medium", "high", "critical"]

# Shared ranking so "does this proposal's risk exceed a customer ceiling"
# can be compared with a plain integer lookup, everywhere that needs it.
RISK_ORDER: dict[str, int] = {"low": 0, "medium": 1, "high": 2, "critical": 3}

_VALID_MAX_RISK_VALUES = {"low", "medium", "high"}


def is_excluded(tags: dict[str, str]) -> bool:
    """cloudcare:exclude=true — never propose anything for this resource,
    regardless of what any rule/agent downstream would otherwise conclude."""
    return str((tags or {}).get("cloudcare:exclude", "")).lower() == "true"


def get_max_risk_ceiling(tags: dict[str, str]) -> RiskLevel | None:
    """cloudcare:max-risk=low|medium|high — a customer-set ceiling on how
    much risk this resource may be auto-executed at. Returns None (no
    ceiling) when the tag is absent or holds a value we don't recognize —
    never guesses a ceiling that wasn't actually set."""
    raw = str((tags or {}).get("cloudcare:max-risk", "")).strip().lower()
    if raw in _VALID_MAX_RISK_VALUES:
        return raw  # type: ignore[return-value]
    return None


def exceeds_max_risk(risk_level: str, tags: dict[str, str]) -> bool:
    """True iff a real, computed risk_level ranks above the resource's
    cloudcare:max-risk ceiling (if any is set). This is an APPROVAL FLOOR,
    not a display cap — callers must never overwrite risk_level itself
    with the ceiling value (that would understate real risk to a human
    reviewer); they should instead force requires_human_approval=True /
    block auto-execution when this returns True."""
    ceiling = get_max_risk_ceiling(tags)
    if ceiling is None:
        return False
    return RISK_ORDER.get(str(risk_level).lower(), 0) > RISK_ORDER[ceiling]


def has_missing_ownership(tags: dict[str, str]) -> bool:
    """True iff neither an Owner nor an Environment tag is present
    (case-insensitive key match) — the doc's definition of 'missing
    ownership', distinct from (and stricter than) the pre-existing
    has_owner_tag check in services/policy/engine.py, which only looks
    at Owner."""
    lowered = {str(k).lower() for k in (tags or {}).keys()}
    return "owner" not in lowered and "environment" not in lowered
